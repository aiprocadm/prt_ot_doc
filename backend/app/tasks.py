"""Celery worker tasks for background document processing."""

from __future__ import annotations

import asyncio
import binascii
import hashlib
import logging
import threading
from datetime import datetime, timedelta, timezone
from time import perf_counter
from typing import Any, Coroutine, TypeVar
from uuid import uuid4

from botocore.exceptions import ClientError
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.metrics import PipelineStage, PipelineType, StageResult, get_metrics
from app.core.payload_constraints import normalize_output_basename
from app.core.tenant import tenant_context
from app.db import AsyncSessionLocal, ensure_tenant_schema, session_scope
from app.domains.files import s3
from app.domains.files.utils import build_dated_prefix
from app.domains.templating.renderer import render_docx
from app.modules.templates.passport import inject_passport
from app.modules.templates.service import build_passport
from app.models.document import (
    Document,
    DocumentBatchItem,
    DocumentBatchItemStatus,
    DocumentBatchRun,
    DocumentBatchStatus,
    DocumentSnapshot,
    DocumentStatus,
    DocumentVersion,
)
from app.models.job_engine import (
    DocumentArtifact,
    DocumentJob,
    DocumentJobStatus,
    DocumentJobStep,
    JobStepStatus,
    OutboxEvent,
    OutboxEventStatus,
)
from app.models.models import (
    Company,
    EdoMessage,
    EdoStatus,
    EdoEnvelopeStatus,
    EdoStatusHistory,
    Person,
    PipelineRun,
    PipelineRunStatus,
    Template,
    TemplateVersion,
    Tenant,
    TrainingPlan,
    User,
    RoleEnum,
    PPEIssue,
    Inspection,
    WebhookDelivery,
    WebhookEndpoint,
)
from app.repository import create_template
from app.modules.headers.engine import apply_headers_to_docx
from app.modules.headers.repo import get_preset_by_code
from app.schemas.template import TemplateCreate, TemplateVersionMetadata
from app.services.audit import AuditService
from app.services.celery_app import celery_app
from app.services.file_storage import FileStorageService
from app.services.idempotency import IdempotencyService, cleanup_idempotency_keys
from app.services.events import EventType
from app.services.obligations import process_task_reminders
from app.services.outbox import OutboxProcessor, OutboxService
from app.services.notifications import send_notification, build_dedup_key
from app.services.reminders import evaluate_due_date
from app.models.notifications import Notification, NotificationChannel, NotificationStatus, NotificationType, ReminderRule, ReminderEntityType, PlanTask, PlanTaskStatus

settings = get_settings()
logger = logging.getLogger(__name__)

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

T = TypeVar("T")


def _run_coroutine(coro: Coroutine[Any, Any, T]) -> T:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    result_holder: dict[str, T] = {}
    error_holder: list[BaseException] = []

    def runner() -> None:
        try:
            result_holder["value"] = asyncio.run(coro)
        except BaseException as exc:  # pragma: no cover - defensive branch
            error_holder.append(exc)

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    thread.join()
    if error_holder:
        raise error_holder[0]
    return result_holder["value"]


RETRYABLE_EXCEPTIONS: tuple[type[BaseException], ...] = (
    ClientError,
    SQLAlchemyError,
    OSError,
    asyncio.TimeoutError,
)


def compute_inbound_dedup_key(payload: dict[str, Any], raw_body: bytes) -> str:
    return str(payload.get("event_id") or payload.get("message_id") or hashlib.sha256(raw_body).hexdigest())


async def _generate_document_for_run(run_id: str, tenant_slug: str) -> tuple[str, str]:
    storage = FileStorageService.default()
    metrics = get_metrics()
    pipeline_start = perf_counter()
    metrics.increment_pipeline_inflight(pipeline=PipelineType.DOCUMENT)
    with tenant_context(tenant_slug):
        ensure_tenant_schema(tenant_slug)
        async with session_scope(tenant=tenant_slug) as session:
            try:
                run = await session.get(PipelineRun, run_id)
                if run is None:
                    raise ValueError("Pipeline run not found")

                metadata = dict(run.result_metadata or {})
                existing_document_id = metadata.get("document_id")
                existing_version_id = metadata.get("document_version_id")
                if run.status is PipelineRunStatus.DONE and existing_document_id:
                    return str(existing_document_id), str(existing_version_id or "")

                company_id = metadata.get("company_id")
                person_id = metadata.get("person_id")
                initiated_by = metadata.get("initiated_by")

                if not company_id or not initiated_by:
                    raise ValueError("Pipeline run metadata is incomplete")

                template_version = await session.get(TemplateVersion, run.template_version_id)
                if template_version is None:
                    raise ValueError("Template version not found")
                if not template_version.payload_key:
                    raise ValueError("Template version payload is missing")

                template = await session.get(Template, run.template_id)
                if template is None:
                    raise ValueError("Template not found")

                company = await session.get(Company, company_id)
                if company is None:
                    raise ValueError("Company not found")

                person = None
                if person_id is not None:
                    person = await session.get(Person, person_id)
                    if person is None:
                        raise ValueError("Person not found")
                    if person.company_id != company.id:
                        raise ValueError("Person does not belong to company")

                user = await session.get(User, initiated_by)
                if user is None:
                    raise ValueError("Initiating user not found")

                run.status = PipelineRunStatus.RUNNING
                run.started_at = datetime.now(tz=timezone.utc)
                run.error = None
                await session.flush()

                context_payload = dict(run.context or {})
                template_bytes = storage.get(template_version.payload_key)

                now = datetime.now(tz=timezone.utc)
                tenant_prefix = build_dated_prefix(tenant_slug, now=now)
                document = Document(
                    tenant_id=run.tenant_id,
                    company_id=company.id,
                    person_id=person.id if person else None,
                    template_id=template.id,
                    template_version_id=template_version.id,
                    status=DocumentStatus.GENERATED,
                    created_by=user.id,
                )
                session.add(document)
                await session.flush()

                output_name = normalize_output_basename(metadata.get("output_name"))
                filename = output_name or uuid4().hex
                storage_key = f"{tenant_prefix}/documents/{document.id}/{filename}.docx"

                correlation_id = str(metadata.get("correlation_id") or run.id)
                passport = build_passport(
                    code=template.name,
                    version=template_version.version,
                    tenant_id=tenant_slug,
                    generated_by=(user.email or user.id),
                    correlation_id=correlation_id,
                    data=context_payload,
                    options={"visible_passport": True},
                    npa_binding_id=str(metadata.get("npa_binding_id")) if metadata.get("npa_binding_id") else None,
                    document_id=document.id,
                    document_version_id=None,
                    version_number=1,
                )

                docx_start = perf_counter()
                metrics.record_pipeline_stage_start(
                    pipeline=PipelineType.DOCUMENT,
                    stage=PipelineStage.DOCX_GENERATED,
                )
                try:
                    rendered_base = render_docx(template_bytes, context_payload)
                    rendered = inject_passport(rendered_base, passport, visible=True)
                except Exception as exc:
                    metrics.record_pipeline_stage_end(
                        pipeline=PipelineType.DOCUMENT,
                        stage=PipelineStage.DOCX_GENERATED,
                        result=StageResult.FAILED,
                        seconds=perf_counter() - docx_start,
                        error_class=exc.__class__.__name__,
                    )
                    raise
                metrics.record_pipeline_stage_end(
                    pipeline=PipelineType.DOCUMENT,
                    stage=PipelineStage.DOCX_GENERATED,
                    result=StageResult.SUCCESS,
                    seconds=perf_counter() - docx_start,
                )

                upload_start = perf_counter()
                metrics.record_pipeline_stage_start(
                    pipeline=PipelineType.DOCUMENT,
                    stage=PipelineStage.STORED_S3,
                )
                try:
                    s3.put_object(data=rendered, mime=DOCX_MIME, key=storage_key)
                except Exception as exc:
                    metrics.record_pipeline_stage_end(
                        pipeline=PipelineType.DOCUMENT,
                        stage=PipelineStage.STORED_S3,
                        result=StageResult.FAILED,
                        seconds=perf_counter() - upload_start,
                        error_class=exc.__class__.__name__,
                    )
                    raise
                metrics.record_pipeline_stage_end(
                    pipeline=PipelineType.DOCUMENT,
                    stage=PipelineStage.STORED_S3,
                    result=StageResult.SUCCESS,
                    seconds=perf_counter() - upload_start,
                )
                document.storage_key = storage_key

                integrity_hash = _sha256_bytes(rendered)
                snapshot = DocumentSnapshot(
                    tenant_id=run.tenant_id,
                    document_id=document.id,
                    template_id=template.id,
                    template_version_id=template_version.id,
                    template_code=template.name,
                    template_version=template_version.version,
                    company_snapshot=_company_snapshot(company),
                    source_refs={
                        "company_id": company.id,
                        "person_id": person.id if person else None,
                        "pipeline_run_id": run.id,
                    },
                    compliance_refs={},
                    render_log={
                        "pipeline_run_id": run.id,
                        "status": "generated",
                        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
                    },
                    integrity_hash=integrity_hash,
                    generated_at=datetime.now(tz=timezone.utc),
                    created_by=user.id,
                )
                session.add(snapshot)
                await session.flush()

                version = DocumentVersion(
                    document=document,
                    template_version=str(template_version.version),
                    data_json={**context_payload, "passport": passport, "correlation_id": correlation_id},
                    file_key=storage_key,
                    template_version_id=template_version.id,
                    snapshot_id=snapshot.id,
                )
                session.add(version)
                await session.flush()

                metadata["correlation_id"] = correlation_id
                metadata["document_id"] = document.id
                metadata["document_version_id"] = version.id
                metadata["docx_storage_key"] = storage_key

                run.status = PipelineRunStatus.DONE
                run.docx_storage_key = storage_key
                run.result_metadata = metadata
                run.outputs = {
                    **(run.outputs or {}),
                    "document_id": document.id,
                    "document_version_id": version.id,
                }
                run.finished_at = datetime.now(tz=timezone.utc)
                metrics.record_pipeline_stage_start(
                    pipeline=PipelineType.DOCUMENT,
                    stage=PipelineStage.STAMPED_QR_APPLIED,
                )
                metrics.record_pipeline_stage_end(
                    pipeline=PipelineType.DOCUMENT,
                    stage=PipelineStage.STAMPED_QR_APPLIED,
                    result=StageResult.SKIPPED,
                    seconds=0.0,
                )
                outbox = OutboxService(session)
                await outbox.enqueue(
                    tenant_id=run.tenant_id,
                    event_type=EventType.DOCUMENT_CREATED.value,
                    payload={
                        "tenant_id": str(run.tenant_id),
                        "actor_id": str(user.id),
                        "occurred_at": document.created_at,
                        "document_id": document.id,
                        "document_version_id": version.id,
                        "template_id": template.id,
                        "template_version_id": template_version.id,
                        "company_id": company.id,
                        "person_id": person.id if person else None,
                        "storage_key": storage_key,
                        "status": document.status.value,
                    },
                )
                await outbox.enqueue(
                    tenant_id=run.tenant_id,
                    event_type=EventType.DOCUMENT_GENERATED.value,
                    idempotency_key=f"{document.id}:{version.id}:generated",
                    payload={
                        "tenant_id": str(run.tenant_id),
                        "actor_id": str(user.id),
                        "occurred_at": document.created_at,
                        "document_id": document.id,
                        "document_version_id": version.id,
                        "template_id": template.id,
                        "template_version_id": template_version.id,
                        "company_id": company.id,
                        "person_id": person.id if person else None,
                        "storage_key": storage_key,
                        "status": document.status.value,
                    },
                )
                idempotency = IdempotencyService(
                    session=session,
                    tenant_id=str(run.tenant_id),
                    endpoint="documents.generate",
                )
                await idempotency.update_document_version_id(
                    key=run.idempotency_key,
                    document_version_id=version.id,
                )
                audit = AuditService(session)
                await audit.log_event(
                    tenant_id=run.tenant_id,
                    action="render_done",
                    object_type="pipeline_run",
                    object_id=run.id,
                    user_id=initiated_by,
                    ip="system",
                    details={
                        "status": "success",
                        "document_id": document.id,
                        "template_id": template.id,
                    },
                )
                await session.flush()
                metrics.record_pipeline_stage_start(
                    pipeline=PipelineType.DOCUMENT,
                    stage=PipelineStage.COMPLETED,
                )
                metrics.record_pipeline_stage_end(
                    pipeline=PipelineType.DOCUMENT,
                    stage=PipelineStage.COMPLETED,
                    result=StageResult.SUCCESS,
                    seconds=0.0,
                )
                metrics.observe_pipeline_total_duration(
                    pipeline=PipelineType.DOCUMENT,
                    seconds=perf_counter() - pipeline_start,
                )
                return str(document.id), str(version.id)
            except Exception as exc:
                metrics.record_pipeline_stage_start(
                    pipeline=PipelineType.DOCUMENT,
                    stage=PipelineStage.FAILED,
                )
                metrics.record_pipeline_stage_end(
                    pipeline=PipelineType.DOCUMENT,
                    stage=PipelineStage.FAILED,
                    result=StageResult.FAILED,
                    seconds=0.0,
                    error_class=exc.__class__.__name__,
                )
                metrics.observe_pipeline_total_duration(
                    pipeline=PipelineType.DOCUMENT,
                    seconds=perf_counter() - pipeline_start,
                )
                raise
            finally:
                metrics.decrement_pipeline_inflight(pipeline=PipelineType.DOCUMENT)


def _company_snapshot(company: Company) -> dict[str, Any]:
    return {
        "id": company.id,
        "name": company.name,
        "inn": company.inn,
        "kpp": company.kpp,
        "ogrn": company.ogrn,
        "activity_type": company.activity_type,
        "okved_codes": list(company.okved_codes or []),
        "legal_address": company.legal_address,
        "actual_address": company.actual_address,
        "director": company.director,
        "bank_name": company.bank_name,
        "bank_bik": company.bank_bik,
        "bank_account": company.bank_account,
        "phone_numbers": list(company.phone_numbers or []),
        "contact_person": company.contact_person,
        "contact_phone": company.contact_phone,
        "contact_email": company.contact_email,
        "email": company.email,
        "work_types": list(company.work_types or []),
        "hazardous_factors": list(company.hazardous_factors or []),
        "is_hazardous_production_facility": company.is_hazardous_production_facility,
        "has_dangerous_objects": company.has_dangerous_objects,
    }


def _sha256_bytes(data: bytes) -> str:
    digest = hashlib.sha256()
    digest.update(data)
    return digest.hexdigest()




@celery_app.task(
    name="app.tasks.register_template",
    autoretry_for=RETRYABLE_EXCEPTIONS,
    retry_backoff=settings.celery.retry_backoff_seconds,
    retry_backoff_max=settings.celery.retry_backoff_max_seconds,
    retry_jitter=True,
    retry_kwargs={"max_retries": settings.celery.task_max_retries},
)
def register_template_task(
    tenant_slug: str,
    name: str,
    storage_key: str,
    checksum_hex: str,
    description: str | None = None,
    metadata: dict[str, Any] | None = None,
    version_metadata: dict[str, Any] | None = None,
) -> str:
    """Persist template metadata and register an active version for a tenant."""

    def decode_checksum() -> bytes:
        try:
            return binascii.unhexlify(checksum_hex)
        except binascii.Error as exc:  # pragma: no cover - validated by caller
            raise ValueError("checksum must be hex-encoded") from exc

    async def _run() -> str:
        payload = TemplateCreate(name=name, description=description, metadata=metadata or {})
        if version_metadata is None:
            raise ValueError("template version metadata is required")
        template_version_metadata = TemplateVersionMetadata.model_validate(version_metadata)
        checksum = decode_checksum()
        with tenant_context(tenant_slug):
            ensure_tenant_schema(tenant_slug)
            async with session_scope(tenant=tenant_slug) as session:
                tenant_row = await session.execute(select(Tenant).where(Tenant.slug == tenant_slug))
                tenant = tenant_row.scalar_one()
                version = await create_template(
                    session,
                    tenant.id,
                    payload,
                    storage_key=storage_key,
                    checksum=checksum,
                    version_metadata=template_version_metadata,
                )
                return str(version.id)

    metrics = get_metrics()
    queue = celery_app.conf.task_default_queue or "default"
    task_name = "app.tasks.register_template"
    metrics.record_celery_enqueue(queue=queue, task=task_name)
    started = perf_counter()
    try:
        result = _run_coroutine(_run())
    except Exception as exc:  # pragma: no cover - Celery surfaces task error
        duration = perf_counter() - started
        metrics.record_celery_execution(
            queue=queue,
            task=task_name,
            status="failed",
            seconds=duration,
            error_code=str(exc) or exc.__class__.__name__,
        )
        logger.exception("register_template_task failed", exc_info=exc)
        raise
    duration = perf_counter() - started
    metrics.record_celery_execution(
        queue=queue,
        task=task_name,
        status="succeeded",
        seconds=duration,
    )
    return result


@celery_app.task(
    name="outbox.dispatch",
    autoretry_for=RETRYABLE_EXCEPTIONS,
    retry_backoff=settings.celery.retry_backoff_seconds,
    retry_backoff_max=settings.celery.retry_backoff_max_seconds,
    retry_jitter=True,
    retry_kwargs={"max_retries": settings.celery.task_max_retries},
)
def dispatch_outbox_task(tenant_slug: str) -> int:
    """Dispatch pending outbox entries for a tenant."""

    async def _run() -> int:
        with tenant_context(tenant_slug):
            ensure_tenant_schema(tenant_slug)
            async with session_scope(tenant=tenant_slug) as session:
                processor = OutboxProcessor(session)
                return await processor.process_once()

    metrics = get_metrics()
    queue = celery_app.conf.task_default_queue or "default"
    task_name = "outbox.dispatch"
    metrics.record_celery_enqueue(queue=queue, task=task_name)
    started = perf_counter()
    try:
        result = _run_coroutine(_run())
    except Exception as exc:  # pragma: no cover - surfaced by Celery in production
        duration = perf_counter() - started
        metrics.record_celery_execution(
            queue=queue,
            task=task_name,
            status="failed",
            seconds=duration,
            error_code=str(exc) or exc.__class__.__name__,
        )
        logger.exception("dispatch_outbox_task failed", exc_info=exc)
        raise

    duration = perf_counter() - started
    metrics.record_celery_execution(
        queue=queue,
        task=task_name,
        status="succeeded",
        seconds=duration,
    )
    return result


@celery_app.task(
    name="tasks.reminders.dispatch",
    autoretry_for=RETRYABLE_EXCEPTIONS,
    retry_backoff=settings.celery.retry_backoff_seconds,
    retry_backoff_max=settings.celery.retry_backoff_max_seconds,
    retry_jitter=True,
    retry_kwargs={"max_retries": settings.celery.task_max_retries},
)
def dispatch_task_reminders() -> int:
    """Process reminder notifications for all active tenants."""

    async def _run() -> int:
        async with AsyncSessionLocal(tenant=settings.default_tenant_slug) as session:
            tenants = list(
                (await session.execute(select(Tenant).where(Tenant.is_active.is_(True))))
                .scalars()
                .all()
            )
        processed = 0
        for tenant in tenants:
            with tenant_context(tenant.slug):
                ensure_tenant_schema(tenant.slug)
                async with session_scope(tenant=tenant.slug) as tenant_session:
                    processed += await process_task_reminders(tenant_session)
        return processed

    metrics = get_metrics()
    queue = celery_app.conf.task_default_queue or "default"
    task_name = "tasks.reminders.dispatch"
    metrics.record_celery_enqueue(queue=queue, task=task_name)
    started = perf_counter()
    try:
        result = _run_coroutine(_run())
    except Exception as exc:  # pragma: no cover - surfaced by Celery in production
        duration = perf_counter() - started
        metrics.record_celery_execution(
            queue=queue,
            task=task_name,
            status="failed",
            seconds=duration,
            error_code=str(exc) or exc.__class__.__name__,
        )
        logger.exception("dispatch_task_reminders failed", exc_info=exc)
        raise

    duration = perf_counter() - started
    metrics.record_celery_execution(
        queue=queue,
        task=task_name,
        status="succeeded",
        seconds=duration,
    )
    return result


@celery_app.task(
    name="idempotency.cleanup",
    autoretry_for=RETRYABLE_EXCEPTIONS,
    retry_backoff=settings.celery.retry_backoff_seconds,
    retry_backoff_max=settings.celery.retry_backoff_max_seconds,
    retry_jitter=True,
    retry_kwargs={"max_retries": settings.celery.task_max_retries},
)
def cleanup_idempotency_keys_task() -> int:
    """Purge stale idempotency records according to the configured TTL."""

    async def _run() -> int:
        async with AsyncSessionLocal(tenant=settings.default_tenant_slug) as session:
            tenants = list(
                (await session.execute(select(Tenant).where(Tenant.is_active.is_(True))))
                .scalars()
                .all()
            )
        total_removed = 0
        for tenant in tenants:
            with tenant_context(tenant.slug):
                ensure_tenant_schema(tenant.slug)
                async with session_scope(tenant=tenant.slug) as tenant_session:
                    total_removed += await cleanup_idempotency_keys(
                        session=tenant_session,
                        ttl_days=settings.idempotency_ttl_days,
                    )
        return total_removed

    metrics = get_metrics()
    queue = celery_app.conf.task_default_queue or "default"
    task_name = "idempotency.cleanup"
    metrics.record_celery_enqueue(queue=queue, task=task_name)
    started = perf_counter()
    try:
        result = _run_coroutine(_run())
    except Exception as exc:  # pragma: no cover - surfaced by Celery in production
        duration = perf_counter() - started
        metrics.record_celery_execution(
            queue=queue,
            task=task_name,
            status="failed",
            seconds=duration,
            error_code=str(exc) or exc.__class__.__name__,
        )
        logger.exception("cleanup_idempotency_keys_task failed", exc_info=exc)
        raise

    duration = perf_counter() - started
    metrics.record_celery_execution(
        queue=queue,
        task=task_name,
        status="succeeded",
        seconds=duration,
    )
    return result


@celery_app.task(
    name="app.tasks.generate_document",
    autoretry_for=RETRYABLE_EXCEPTIONS,
    retry_backoff=settings.celery.retry_backoff_seconds,
    retry_backoff_max=settings.celery.retry_backoff_max_seconds,
    retry_jitter=True,
    retry_kwargs={"max_retries": settings.celery.task_max_retries},
)
def generate_document_task(run_id: str, *, tenant_slug: str) -> str:
    """Render a document for the provided pipeline run and persist the result."""

    async def _run() -> str:
        document_id, _version_id = await _generate_document_for_run(run_id, tenant_slug)
        return document_id

    metrics = get_metrics()
    queue = celery_app.conf.task_default_queue or "default"
    task_name = "app.tasks.generate_document"
    metrics.record_celery_enqueue(queue=queue, task=task_name)
    started = perf_counter()
    try:
        result = _run_coroutine(_run())
    except Exception as exc:  # pragma: no cover - surfaced by Celery in production
        duration = perf_counter() - started
        metrics.record_celery_execution(
            queue=queue,
            task=task_name,
            status="failed",
            seconds=duration,
            error_code=str(exc) or exc.__class__.__name__,
        )
        logger.exception("generate_document_task failed", exc_info=exc)

        async def _mark_failed(exception: Exception = exc) -> None:
            with tenant_context(tenant_slug):
                ensure_tenant_schema(tenant_slug)
                async with session_scope(tenant=tenant_slug) as session:
                    run = await session.get(PipelineRun, run_id)
                    if run:
                        run.status = PipelineRunStatus.ERROR
                        run.error = str(exception)[:255]
                        run.finished_at = datetime.now(tz=timezone.utc)
                        audit = AuditService(session)
                        await audit.log_event(
                            tenant_id=run.tenant_id,
                            action="render_done",
                            object_type="pipeline_run",
                            object_id=run.id,
                            user_id=(
                                run.result_metadata.get("initiated_by")
                                if run.result_metadata
                                else None
                            ),
                            ip="system",
                            details={"status": "error", "error": str(exception)[:255]},
                        )

        try:
            _run_coroutine(_mark_failed())
        finally:
            raise

    duration = perf_counter() - started
    metrics.record_celery_execution(
        queue=queue,
        task=task_name,
        status="succeeded",
        seconds=duration,
    )
    return result


@celery_app.task(
    name="app.tasks.generate_document_batch_item",
    autoretry_for=RETRYABLE_EXCEPTIONS,
    retry_backoff=settings.celery.retry_backoff_seconds,
    retry_backoff_max=settings.celery.retry_backoff_max_seconds,
    retry_jitter=True,
    retry_kwargs={"max_retries": settings.celery.task_max_retries},
)
def generate_document_batch_item_task(batch_id: str, item_id: str, *, tenant_slug: str) -> str:
    """Process a single batch item."""

    async def _run() -> str:
        with tenant_context(tenant_slug):
            ensure_tenant_schema(tenant_slug)
            async with session_scope(tenant=tenant_slug) as session:
                batch = await session.get(DocumentBatchRun, batch_id)
                item = await session.get(DocumentBatchItem, item_id)
                if batch is None or item is None:
                    raise ValueError("Batch item not found")
                if item.status is DocumentBatchItemStatus.SUCCEEDED:
                    return str(item.document_id or "")

                item.status = DocumentBatchItemStatus.RUNNING
                item.started_at = datetime.now(tz=timezone.utc)
                batch.status = DocumentBatchStatus.RUNNING
                if batch.started_at is None:
                    batch.started_at = datetime.now(tz=timezone.utc)
                await session.flush()

                if not item.pipeline_run_id:
                    raise ValueError("Pipeline run not assigned for batch item")

            document_id, version_id = await _generate_document_for_run(
                item.pipeline_run_id, tenant_slug
            )

            async with session_scope(tenant=tenant_slug) as session:
                batch = await session.get(DocumentBatchRun, batch_id)
                item = await session.get(DocumentBatchItem, item_id)
                if batch is None or item is None:
                    raise ValueError("Batch item not found")

                item.status = DocumentBatchItemStatus.SUCCEEDED
                item.finished_at = datetime.now(tz=timezone.utc)
                item.document_id = document_id
                item.document_version_id = version_id
                batch.processed += 1
                batch.succeeded += 1
                if batch.processed >= batch.total:
                    batch.status = DocumentBatchStatus.DONE
                    batch.finished_at = datetime.now(tz=timezone.utc)
                await session.flush()
                return document_id

    metrics = get_metrics()
    queue = celery_app.conf.task_default_queue or "default"
    task_name = "app.tasks.generate_document_batch_item"
    metrics.record_celery_enqueue(queue=queue, task=task_name)
    started = perf_counter()
    try:
        result = _run_coroutine(_run())
    except Exception as exc:  # pragma: no cover - Celery surfaces task error
        duration = perf_counter() - started
        metrics.record_celery_execution(
            queue=queue,
            task=task_name,
            status="failed",
            seconds=duration,
            error_code=str(exc) or exc.__class__.__name__,
        )
        logger.exception("generate_document_batch_item_task failed", exc_info=exc)
        with tenant_context(tenant_slug):
            ensure_tenant_schema(tenant_slug)
            _run_coroutine(_mark_batch_item_failed(batch_id, item_id, str(exc), tenant_slug))
        raise
    duration = perf_counter() - started
    metrics.record_celery_execution(
        queue=queue,
        task=task_name,
        status="succeeded",
        seconds=duration,
    )
    return result


async def _mark_batch_item_failed(
    batch_id: str, item_id: str, error: str, tenant_slug: str
) -> None:
    async with session_scope(tenant=tenant_slug) as session:
        batch = await session.get(DocumentBatchRun, batch_id)
        item = await session.get(DocumentBatchItem, item_id)
        if batch is None or item is None:
            return
        item.status = DocumentBatchItemStatus.FAILED
        item.error = error[:255]
        item.finished_at = datetime.now(tz=timezone.utc)
        batch.processed += 1
        batch.failed += 1
        if batch.processed >= batch.total:
            batch.status = DocumentBatchStatus.FAILED
            batch.finished_at = datetime.now(tz=timezone.utc)
        await session.flush()


@celery_app.task(name="dispatch_outbox_events")
def dispatch_outbox_events(max_attempts: int | None = None, tenant_slug: str = "test") -> int:
    return _run_coroutine(_dispatch_outbox_events(max_attempts=max_attempts, tenant_slug=tenant_slug))


def _compute_outbox_backoff(attempts: int) -> timedelta:
    base = max(int(settings.outbox_retry_backoff_seconds), 1)
    cap = max(int(settings.outbox_retry_backoff_max_seconds), base)
    jitter = min(attempts, 5)
    seconds = min((2 ** max(attempts - 1, 0)) * base + jitter, cap)
    return timedelta(seconds=seconds)


async def _dispatch_outbox_events(*, max_attempts: int | None = None, tenant_slug: str = "test") -> int:
    import hmac
    import json

    import httpx

    processed = 0
    now = datetime.now(tz=timezone.utc)
    limit = int(max_attempts or settings.outbox_max_attempts)
    async with session_scope(tenant=tenant_slug) as session:
        pending = (
            await session.execute(
                select(OutboxEvent)
                .where(
                    OutboxEvent.status.in_([OutboxEventStatus.PENDING.value, OutboxEventStatus.FAILED.value]),
                    (OutboxEvent.next_attempt_at.is_(None)) | (OutboxEvent.next_attempt_at <= now),
                )
                .order_by(OutboxEvent.created_at.asc())
                .with_for_update(skip_locked=True)
                .limit(100)
            )
        ).scalars().all()
        for event in pending:
            event.status = OutboxEventStatus.PROCESSING.value
        await session.flush()

        endpoints = (
            await session.execute(select(WebhookEndpoint).where(WebhookEndpoint.tenant_id == tenant_slug, WebhookEndpoint.is_enabled.is_(True)))
        ).scalars().all()
        async with httpx.AsyncClient(timeout=10.0) as client:
            for event in pending:
                event.attempts += 1
                correlation_id = str((event.headers or {}).get("correlation_id") or (event.payload or {}).get("correlation_id") or event.id)
                if event.event_type in {"DocumentGenerated", "DocumentExported", "DocumentSigned", "RiskAssessed", "PPEIssued", "TrainingCompleted"}:
                    actor_id = str((event.payload or {}).get("actor_id") or "")
                    if actor_id:
                        mapped = {
                            "DocumentGenerated": NotificationType.DOCUMENT_GENERATED,
                            "DocumentExported": NotificationType.DOCUMENT_EXPORTED,
                            "DocumentSigned": NotificationType.DOCUMENT_SIGNED,
                            "TrainingCompleted": NotificationType.TRAINING_COMPLETED,
                            "PPEIssued": NotificationType.PPE_ISSUE_CREATED,
                            "RiskAssessed": NotificationType.CA_DUE_SOON,
                        }[event.event_type]
                        tenant_row = (await session.execute(select(Tenant).where(Tenant.slug == tenant_slug))).scalar_one_or_none()
                        resolved_tenant_id = str(tenant_row.id) if tenant_row is not None else str(event.tenant_id)
                        await send_notification(
                            session,
                            tenant_id=resolved_tenant_id,
                            user_id=actor_id,
                            channel=NotificationChannel.INAPP,
                            type=mapped,
                            title=event.event_type,
                            body="Событие из outbox",
                            payload={"event_id": event.event_id, "entity_type": "outbox_event", "entity_id": event.id},
                            dedup_key=f"outbox:{event.event_id}:inapp",
                        )
                body = {
                    "event_id": event.event_id,
                    "event_type": event.event_type,
                    "tenant_id": event.tenant_id,
                    "payload": event.payload,
                    "headers": event.headers or {},
                    "correlation_id": correlation_id,
                }
                raw_body = json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
                matching = [ep for ep in endpoints if not ep.subscribed_events or event.event_type in (ep.subscribed_events or [])]
                success = not bool((event.payload or {}).get("force_fail"))
                for ep in matching:
                    delivered = WebhookDelivery(
                        tenant_id=event.tenant_id,
                        endpoint_id=ep.id,
                        event_id=event.event_id,
                        status="processing",
                        attempts=event.attempts,
                        started_at=datetime.now(tz=timezone.utc),
                    )
                    session.add(delivered)
                    ts = str(int(datetime.now(tz=timezone.utc).timestamp()))
                    signature = hmac.new((ep.secret or "").encode("utf-8"), f"{ts}.".encode("utf-8") + raw_body, hashlib.sha256).hexdigest()
                    headers = {
                        "Content-Type": "application/json",
                        "X-Event-Id": event.event_id,
                        "X-Event-Type": event.event_type,
                        "X-Tenant": event.tenant_id,
                        "X-Correlation-Id": correlation_id,
                        "X-Signature": f"v1={signature}",
                        "X-Signature-Ts": ts,
                    }
                    try:
                        resp = await client.post(ep.url, content=raw_body, headers=headers, timeout=max(ep.timeout_ms / 1000, 0.1))
                        delivered.status = "success" if 200 <= resp.status_code < 300 else "failed"
                        delivered.last_status_code = resp.status_code
                        delivered.last_response_body = (resp.text or "")[:1000]
                        delivered.ended_at = datetime.now(tz=timezone.utc)
                        delivered.delivered_at = delivered.ended_at if delivered.status == "success" else None
                        if delivered.status != "success":
                            success = False
                    except Exception as exc:
                        delivered.status = "failed"
                        delivered.last_error = {"message": str(exc)}
                        delivered.ended_at = datetime.now(tz=timezone.utc)
                        success = False
                if success:
                    event.status = OutboxEventStatus.SENT.value
                    event.sent_at = datetime.now(tz=timezone.utc)
                    event.next_attempt_at = None
                    event.last_error = None
                    processed += 1
                elif event.attempts >= limit:
                    event.status = OutboxEventStatus.POISONED.value
                    event.next_attempt_at = None
                    event.last_error = "poisoned_after_max_attempts"
                else:
                    event.status = OutboxEventStatus.FAILED.value
                    event.next_attempt_at = datetime.now(tz=timezone.utc) + _compute_outbox_backoff(event.attempts)
                    event.last_error = "delivery_failed_retry_scheduled"
        await session.flush()
    return processed




@celery_app.task(name="notifications.dispatch")
def dispatch_notification_job(notification_id: str, tenant_slug: str = "test") -> int:
    return _run_coroutine(_dispatch_notification_job(notification_id=notification_id, tenant_slug=tenant_slug))


async def _dispatch_notification_job(*, notification_id: str, tenant_slug: str = "test") -> int:
    async with session_scope(tenant=tenant_slug) as session:
        notification = (await session.execute(select(Notification).where(Notification.id == notification_id))).scalar_one_or_none()
        if notification is None:
            return 0
        if notification.status != NotificationStatus.QUEUED:
            return 0
        try:
            if notification.channel == NotificationChannel.INAPP:
                notification.status = NotificationStatus.SENT
                notification.sent_at = datetime.now(tz=timezone.utc)
            elif notification.channel == NotificationChannel.EMAIL:
                notification.status = NotificationStatus.SENT
                notification.sent_at = datetime.now(tz=timezone.utc)
            else:
                notification.status = NotificationStatus.SENT
                notification.sent_at = datetime.now(tz=timezone.utc)
            notification.attempts += 1
        except Exception as exc:  # pragma: no cover
            notification.attempts += 1
            notification.status = NotificationStatus.FAILED
            notification.last_error = str(exc)
        await session.flush()
    return 1


@celery_app.task(name="reminders.scan")
def scan_reminders_job() -> int:
    return _run_coroutine(_scan_reminders_job())


async def _resolve_rule_recipients(*, session: AsyncSession, tenant_id: str, rule: ReminderRule, default_user_id: str | None) -> list[str]:
    recipients = rule.recipients or {}
    mode = str(recipients.get("mode") or "assignees")
    resolved: set[str] = set()
    if mode in {"assignees", "managers"} and default_user_id:
        resolved.add(default_user_id)
    if mode in {"role", "managers"}:
        roles = [str(role).lower() for role in recipients.get("roles", [])]
        if mode == "managers" and not roles:
            roles = [RoleEnum.ADMIN.value]
        if roles:
            users = (
                await session.execute(
                    select(User).where(
                        User.tenant_id == tenant_id,
                        User.deleted_at.is_(None),
                        User.role.in_(roles),
                    )
                )
            ).scalars().all()
            resolved.update(user.id for user in users)
    if mode == "explicit":
        explicit = [str(user_id) for user_id in recipients.get("user_ids", [])]
        resolved.update(explicit)
    return list(resolved)


async def _scan_reminders_for_tenant(*, tenant_slug: str, now: datetime) -> int:
    processed = 0
    async with session_scope(tenant=tenant_slug) as session:
        rules = (
            await session.execute(
                select(ReminderRule).where(ReminderRule.is_enabled.is_(True), ReminderRule.deleted_at.is_(None))
            )
        ).scalars().all()
        for rule in rules:
            entity_type_value = rule.entity_type.value if hasattr(rule.entity_type, "value") else str(rule.entity_type)
            offsets = [int(x) for x in (rule.schedule or {}).get("offsets_days", [30, 14, 7, 1, 0])]
            escalation_days = int(((rule.schedule or {}).get("escalation") or {}).get("after_days", 3))
            if entity_type_value == ReminderEntityType.TRAINING.value:
                rows = (
                    await session.execute(select(TrainingPlan).where(TrainingPlan.due_date.is_not(None), TrainingPlan.deleted_at.is_(None)))
                ).scalars().all()
                for training in rows:
                    if not training.due_date:
                        continue
                    evaluation = evaluate_due_date(due_date=training.due_date, today=now.date(), offsets_days=offsets)
                    if evaluation is None:
                        continue
                    due_dt = datetime.combine(training.due_date, datetime.min.time(), tzinfo=timezone.utc)
                    recipients = await _resolve_rule_recipients(
                        session=session,
                        tenant_id=rule.tenant_id,
                        rule=rule,
                        default_user_id=training.person_id or training.created_by,
                    )
                    status = PlanTaskStatus.OVERDUE if evaluation.is_overdue else PlanTaskStatus.OPEN
                    if bool((rule.action or {}).get("create_task", True)) and recipients:
                        assignee = recipients[0]
                        task = (
                            await session.execute(
                                select(PlanTask).where(
                                    PlanTask.tenant_id == rule.tenant_id,
                                    PlanTask.entity_type == "training",
                                    PlanTask.entity_id == training.id,
                                    PlanTask.assignee_id == assignee,
                                    PlanTask.deleted_at.is_(None),
                                )
                            )
                        ).scalar_one_or_none()
                        if task is None:
                            session.add(
                                PlanTask(
                                    tenant_id=rule.tenant_id,
                                    title=f"Training due: {training.id}",
                                    description="Autogenerated from reminder rule",
                                    entity_type="training",
                                    entity_id=training.id,
                                    assignee_id=assignee,
                                    status=status,
                                    due_at=due_dt,
                                )
                            )
                        else:
                            task.status = status
                            task.due_at = due_dt
                    if bool((rule.action or {}).get("notify", True)):
                        for user_id in recipients:
                            n_type = NotificationType.TRAINING_OVERDUE if evaluation.is_overdue else NotificationType.TRAINING_DUE_SOON
                            effective_offset = -escalation_days if evaluation.is_overdue else evaluation.offset_day
                            dedup_key = f"{rule.tenant_id}:{rule.code}:{training.id}:{due_dt.date().isoformat()}:{effective_offset}:inapp:{user_id}"
                            await send_notification(
                                session,
                                tenant_id=rule.tenant_id,
                                user_id=user_id,
                                channel=NotificationChannel.INAPP,
                                type=n_type,
                                title="Контрольная дата обучения",
                                body="Проверьте дедлайн обучения",
                                payload={"entity_type": "training", "entity_id": training.id, "deeplink": f"/training?id={training.id}"},
                                dedup_key=dedup_key,
                            )
                    processed += 1
            elif entity_type_value == ReminderEntityType.PPE.value:
                rows = (
                    await session.execute(select(PPEIssue).where(PPEIssue.expires_at.is_not(None), PPEIssue.deleted_at.is_(None)))
                ).scalars().all()
                for issue in rows:
                    due_date = issue.expires_at.date() if issue.expires_at else None
                    if not due_date:
                        continue
                    evaluation = evaluate_due_date(due_date=due_date, today=now.date(), offsets_days=offsets)
                    if evaluation is None:
                        continue
                    recipients = await _resolve_rule_recipients(
                        session=session,
                        tenant_id=rule.tenant_id,
                        rule=rule,
                        default_user_id=issue.created_by,
                    )
                    for user_id in recipients:
                        dedup_key = f"{rule.tenant_id}:{rule.code}:{issue.id}:{due_date.isoformat()}:{evaluation.offset_day}:inapp:{user_id}"
                        await send_notification(
                            session,
                            tenant_id=rule.tenant_id,
                            user_id=user_id,
                            channel=NotificationChannel.INAPP,
                            type=NotificationType.PPE_EXPIRY_SOON,
                            title="Срок действия СИЗ",
                            body="Требуется продление или переоформление СИЗ",
                            payload={"entity_type": "ppe", "entity_id": issue.id, "deeplink": f"/ppe?issue={issue.id}"},
                            dedup_key=dedup_key,
                        )
                    processed += 1
            elif entity_type_value == ReminderEntityType.INSPECTION.value:
                rows = (
                    await session.execute(select(Inspection).where(Inspection.scheduled_at.is_not(None), Inspection.deleted_at.is_(None)))
                ).scalars().all()
                for inspection in rows:
                    if not inspection.scheduled_at:
                        continue
                    evaluation = evaluate_due_date(due_date=inspection.scheduled_at, today=now.date(), offsets_days=offsets)
                    if evaluation is None:
                        continue
                    recipients = await _resolve_rule_recipients(
                        session=session,
                        tenant_id=rule.tenant_id,
                        rule=rule,
                        default_user_id=inspection.responsible_id,
                    )
                    ntype = NotificationType.INSPECTION_OVERDUE if evaluation.is_overdue else NotificationType.INSPECTION_PLANNED
                    for user_id in recipients:
                        dedup_key = f"{rule.tenant_id}:{rule.code}:{inspection.id}:{inspection.scheduled_at.isoformat()}:{evaluation.offset_day}:inapp:{user_id}"
                        await send_notification(
                            session,
                            tenant_id=rule.tenant_id,
                            user_id=user_id,
                            channel=NotificationChannel.INAPP,
                            type=ntype,
                            title="Проверка по графику",
                            body="Контрольная дата проверки",
                            payload={"entity_type": "inspection", "entity_id": inspection.id, "deeplink": f"/inspections?id={inspection.id}"},
                            dedup_key=dedup_key,
                        )
                    processed += 1
        await session.flush()
    return processed


async def _scan_reminders_job() -> int:
    now = datetime.now(tz=timezone.utc)
    async with AsyncSessionLocal(tenant=settings.default_tenant_slug) as session:
        tenants = list((await session.execute(select(Tenant).where(Tenant.is_active.is_(True)))).scalars().all())
    processed = 0
    for tenant in tenants:
        with tenant_context(tenant.slug):
            ensure_tenant_schema(tenant.slug)
            processed += await _scan_reminders_for_tenant(tenant_slug=tenant.slug, now=now)
    return processed


@celery_app.task(name="process_inbound_webhook")
def process_inbound_webhook(*, source: str, tenant_slug: str, payload: dict[str, Any]) -> int:
    return _run_coroutine(_process_inbound_webhook(source=source, tenant_slug=tenant_slug, payload=payload))


async def _process_inbound_webhook(*, source: str, tenant_slug: str, payload: dict[str, Any]) -> int:
    from app.models.document import DocumentVersion, DocumentVersionStatus
    from app.models.models import EdoEnvelope, EdoEnvelopeStatus

    async with session_scope(tenant=tenant_slug) as session:
        if source != "edo":
            return 0
        external_id = str(payload.get("external_id") or "")
        status_value = str(payload.get("status") or "").lower()
        if not external_id or not status_value:
            return 0

        status_map = {
            "queued": EdoEnvelopeStatus.QUEUED,
            "sent": EdoEnvelopeStatus.SENT,
            "delivered": EdoEnvelopeStatus.DELIVERED,
            "signed": EdoEnvelopeStatus.SIGNED,
            "rejected": EdoEnvelopeStatus.REJECTED,
            "failed": EdoEnvelopeStatus.FAILED,
            "accepted": EdoEnvelopeStatus.SIGNED,
        }
        target_status = status_map.get(status_value)
        if target_status is None:
            return 0

        envelope = (
            await session.execute(
                select(EdoEnvelope).where(EdoEnvelope.tenant_id == tenant_slug, EdoEnvelope.external_id == external_id)
            )
        ).scalar_one_or_none()
        message = (
            await session.execute(
                select(EdoMessage).where(EdoMessage.tenant_id == tenant_slug, EdoMessage.external_id == external_id)
            )
        ).scalar_one_or_none()
        if envelope is None and message is None:
            return 0

        changed = 0
        if envelope is not None:
            current = envelope.status
            rank = {
                EdoEnvelopeStatus.QUEUED: 0,
                EdoEnvelopeStatus.SENT: 1,
                EdoEnvelopeStatus.DELIVERED: 2,
                EdoEnvelopeStatus.SIGNED: 3,
                EdoEnvelopeStatus.REJECTED: 3,
                EdoEnvelopeStatus.FAILED: 3,
            }
            if rank[target_status] > rank[current]:
                envelope.status = target_status
                envelope.last_event_at = datetime.now(tz=timezone.utc)
                changed += 1
                if envelope.object_type == "document_version":
                    version = await session.get(DocumentVersion, envelope.object_id)
                    if version is not None and target_status in {EdoEnvelopeStatus.SIGNED, EdoEnvelopeStatus.DELIVERED}:
                        version.status = DocumentVersionStatus.PUBLISHED
        if message is not None:
            msg_map = {
                EdoEnvelopeStatus.QUEUED: EdoStatus.QUEUED,
                EdoEnvelopeStatus.SENT: EdoStatus.SENT,
                EdoEnvelopeStatus.DELIVERED: EdoStatus.DELIVERED,
                EdoEnvelopeStatus.SIGNED: EdoStatus.ACCEPTED,
                EdoEnvelopeStatus.REJECTED: EdoStatus.REJECTED,
                EdoEnvelopeStatus.FAILED: EdoStatus.FAILED,
            }
            message_target = msg_map[target_status]
            if message.status != message_target:
                message.status = message_target
                changed += 1
                session.add(
                    EdoStatusHistory(
                        tenant_id=tenant_slug,
                        edo_message_id=message.id,
                        status=message_target,
                        raw_payload_json=payload,
                    )
                )

        if changed == 0:
            return 0

        await AuditService(session).log_event(
            tenant_id=tenant_slug,
            action="edo_status_update",
            object_type="EdoEnvelope" if envelope is not None else "EdoMessage",
            object_id=(envelope.id if envelope is not None else message.id),
            actor_type="service",
            ip="system",
            request_id=str(payload.get("correlation_id") or payload.get("event_id") or uuid4()),
            changed_fields=None,
            details={"source": source, "status": target_status.value, "external_id": external_id},
        )
        if target_status == EdoEnvelopeStatus.SIGNED and envelope is not None:
            await OutboxService(session).add_event(
                tenant_id=tenant_slug,
                event_type="Signed",
                aggregate_type="edo_envelope",
                aggregate_id=envelope.id,
                payload={
                    "tenant_id": tenant_slug,
                    "event_id": str(uuid4()),
                    "document_id": envelope.object_id,
                    "document_version_id": envelope.object_id,
                    "status": "signed",
                    "signed_at": datetime.now(timezone.utc).isoformat(),
                    "correlation_id": payload.get("correlation_id"),
                },
                headers={"correlation_id": payload.get("correlation_id"), "produced_by": "inbound_webhook", "schema_version": 1},
            )
        return 1


@celery_app.task(name="app.tasks.apply_headers_job")
def apply_headers_job(*, job_id: str, tenant_slug: str) -> dict[str, str]:
    async def _run() -> dict[str, str]:
        storage = FileStorageService.default()
        with tenant_context(tenant_slug):
            ensure_tenant_schema(tenant_slug)
            async with session_scope(tenant=tenant_slug) as session:
                job = await session.get(DocumentJob, job_id)
                if job is None:
                    raise ValueError("Job not found")
                step = (
                    await session.execute(
                        select(DocumentJobStep).where(
                            DocumentJobStep.job_id == job.id,
                            DocumentJobStep.step_code == "apply_headers",
                        )
                    )
                ).scalar_one()
                payload = step.input_ref or {}
                version = await session.get(DocumentVersion, payload.get("document_version_id"))
                if version is None:
                    raise ValueError("Document version not found")
                preset = await get_preset_by_code(
                    session, tenant_id=str(job.tenant_id), code=str(payload.get("preset_code"))
                )
                if preset is None:
                    raise ValueError("Preset not found")

                job.status = DocumentJobStatus.RUNNING.value
                step.status = JobStepStatus.RUNNING.value
                step.started_at = datetime.now(tz=timezone.utc)
                await session.flush()

                source = storage.get(version.file_key)
                output, report = apply_headers_to_docx(
                    docx_bytes=source,
                    preset=preset,
                    context=payload.get("context") or {},
                    watermark_override=payload.get("watermark_override"),
                )
                new_key = f"{version.file_key.rsplit('.', 1)[0]}_with_headers.docx"
                storage.put(new_key, output, content_type=DOCX_MIME)

                max_version = await session.scalar(
                    select(DocumentVersion.version_number)
                    .where(DocumentVersion.document_id == version.document_id)
                    .order_by(DocumentVersion.version_number.desc())
                    .limit(1)
                )
                new_version = DocumentVersion(
                    tenant_id=version.tenant_id,
                    document_id=version.document_id,
                    snapshot_id=version.snapshot_id,
                    template_version=version.template_version,
                    data_json=version.data_json,
                    file_key=new_key,
                    file_id=None,
                    template_version_id=version.template_version_id,
                    version_number=int(max_version or 1) + 1,
                )
                session.add(new_version)
                await session.flush()
                session.add(
                    DocumentArtifact(
                        tenant_id=str(job.tenant_id),
                        job_id=job.id,
                        step_code="apply_headers",
                        kind="docx",
                        file_id=None,
                        sha256=hashlib.sha256(output).hexdigest(),
                        meta={"file_key": new_key},
                    )
                )

                step.status = JobStepStatus.SUCCESS.value
                step.ended_at = datetime.now(tz=timezone.utc)
                step.output_ref = {
                    "document_version_id": new_version.id,
                    "report": report.model_dump(),
                }
                job.status = DocumentJobStatus.SUCCESS.value
                job.result_document_version_id = new_version.id
                job.ended_at = datetime.now(tz=timezone.utc)
                await session.flush()
                return {"job_id": job.id, "document_version_id": new_version.id}

    return _run_coroutine(_run())


@celery_app.task(name="app.tasks.convert_pdf_job")
def convert_pdf_job(*, tenant_id: str, input_file_id: str, pdf_run_id: str, options: dict, correlation_id: str | None = None) -> dict[str, object]:
    async def _run() -> dict[str, object]:
        from datetime import datetime, timedelta, timezone
        from sqlalchemy import select

        from app.models.file import File
        from app.modules.pdf.convert import (
            build_pdf_file,
            convert_docx_bytes,
            load_source_bytes,
            map_failure,
            persist_pdf,
        )
        from app.modules.pdf.models import PdfConversionRun, PdfRunStatus
        from app.modules.pdf.service_pool import LibreOfficePool

        timeout_s = int((options or {}).get("timeout_s") or 45)
        pool = LibreOfficePool(workers=4)
        attempts = 0
        last_error: Exception | None = None

        with tenant_context(tenant_id):
            ensure_tenant_schema(tenant_id)
            async with session_scope(tenant=tenant_id) as session:
                run = await session.get(PdfConversionRun, pdf_run_id)
                if run is None:
                    return {"status": "missing_run"}
                run.status = PdfRunStatus.RUNNING.value
                run.started_at = datetime.now(timezone.utc)
                await session.flush()

            for _ in range(2):
                attempts += 1
                try:
                    async with session_scope(tenant=tenant_id) as session:
                        source = await session.get(File, input_file_id)
                        run = await session.get(PdfConversionRun, pdf_run_id)
                        if source is None or run is None:
                            return {"status": "missing_input"}

                        source_bytes = load_source_bytes(source)
                        pdf_bytes, sha256_hex = convert_docx_bytes(source_bytes=source_bytes, timeout_s=timeout_s, pool=pool)

                        existing = (
                            await session.execute(
                                select(File).where(
                                    File.tenant_id == tenant_id,
                                    File.sha256 == sha256_hex,
                                    File.mime == "application/pdf",
                                )
                            )
                        ).scalar_one_or_none()

                        if existing is None:
                            tenant_prefix = str(source.storage_key).split("/", 1)[0]
                            key, _ = persist_pdf(
                                tenant_prefix=tenant_prefix,
                                source=source,
                                pdf_bytes=pdf_bytes,
                                sha256_hex=sha256_hex,
                            )
                            existing = build_pdf_file(
                                tenant_id=tenant_id,
                                key=key,
                                sha256_hex=sha256_hex,
                                size=len(pdf_bytes),
                            )
                            session.add(existing)
                            await session.flush()

                        run.output_file_id = existing.id
                        run.attempts = attempts
                        run.status = PdfRunStatus.SUCCESS.value
                        run.ended_at = datetime.now(timezone.utc)
                        run.error_code = None
                        run.error_payload = {}
                        await session.flush()
                        index_file_content_job.apply_async(kwargs={"tenant_slug": tenant_id, "file_id": existing.id}, countdown=0)
                        return {"status": "success", "output_file_id": existing.id, "attempts": attempts}
                except Exception as exc:  # noqa: BLE001
                    last_error = exc
                    logger.exception("pdf.convert.failed", extra={"attempt": attempts, "correlation_id": correlation_id})

            async with session_scope(tenant=tenant_id) as session:
                run = await session.get(PdfConversionRun, pdf_run_id)
                if run is not None:
                    run.attempts = attempts
                    run.status = PdfRunStatus.FAILED.value
                    run.ended_at = datetime.now(timezone.utc)
                    run.error_code = map_failure(last_error) if last_error else "PDF_CONVERSION_FAILED"
                    run.error_payload = {"error": str(last_error)[:500]} if last_error else {}
                    await session.flush()
            return {"status": "failed", "attempts": attempts}

    return _run_coroutine(_run())


@celery_app.task(name="files.index_content", bind=True, max_retries=3, default_retry_delay=30)
def index_file_content_job(self, tenant_slug: str, version_id: str | None = None, file_id: str | None = None):
    async def _run() -> dict[str, str]:
        from app.modules.files.service import index_file_version, index_file_record

        with tenant_context(tenant_slug):
            ensure_tenant_schema(tenant_slug)
            async with session_scope(tenant=tenant_slug) as session:
                tenant_id = str(session.info.get("tenant_id") or "")
                if not tenant_id:
                    tenant = (await session.execute(select(Tenant).where(Tenant.slug == tenant_slug))).scalar_one_or_none()
                    if tenant is None:
                        return {"status": "tenant_missing"}
                    tenant_id = str(tenant.id)
                if version_id:
                    await index_file_version(session, tenant_id=tenant_id, version_id=version_id)
                if file_id:
                    await index_file_record(session, tenant_id=tenant_id, file_id=file_id)
                await session.flush()
                outbox = OutboxService(session)
                await outbox.enqueue(
                    tenant_id=tenant_id,
                    event_type=EventType.EDO_STATUS_CHANGED.value,
                    payload={
                        "tenant_id": tenant_id,
                        "occurred_at": datetime.now(timezone.utc),
                        "metadata": {"event": "FileIndexed", "version_id": version_id, "file_id": file_id},
                    },
                )
                return {"status": "ok", "version_id": version_id or "", "file_id": file_id or ""}

    try:
        return _run_coroutine(_run())
    except RETRYABLE_EXCEPTIONS as exc:
        raise self.retry(exc=exc)


@celery_app.task(name="files.av_scan_file_job")
def av_scan_file_job(tenant_id: str, file_id: str) -> str:
    from app.modules.files.tasks import av_scan_file_job as _delegate

    return _delegate(tenant_id, file_id)

@celery_app.task(name="billing.recompute_active_workers")
def recompute_active_workers_job(tenant_slug: str) -> dict[str, int | str]:
    async def _run() -> dict[str, int | str]:
        from sqlalchemy import func

        from app.models.models import EmploymentStatus
        from app.services.billing import BillingService, current_period_yyyymm

        with tenant_context(tenant_slug):
            ensure_tenant_schema(tenant_slug)
            async with session_scope(tenant=tenant_slug) as session:
                tenant_id = str(session.info.get("tenant_id") or "")
                if not tenant_id:
                    tenant = (await session.execute(select(Tenant).where(Tenant.slug == tenant_slug))).scalar_one_or_none()
                    if tenant is None:
                        return {"status": "tenant_missing", "active_workers": 0}
                    tenant_id = str(tenant.id)

                active_workers = int(
                    (
                        await session.execute(
                            select(func.count(Person.id)).where(
                                Person.tenant_id == tenant_id,
                                Person.deleted_at.is_(None),
                                Person.employment_status == EmploymentStatus.ACTIVE,
                            )
                        )
                    ).scalar_one()
                    or 0
                )
                service = BillingService(session)
                usage = await service.ensure_usage_row(
                    tenant_id=tenant_id,
                    period_yyyymm=current_period_yyyymm(),
                )
                usage.active_workers = active_workers
                await session.flush()
                return {
                    "status": "ok",
                    "tenant_id": tenant_id,
                    "active_workers": active_workers,
                    "period_yyyymm": usage.period_yyyymm,
                }

    return _run_coroutine(_run())


@celery_app.task(name="approval_deadline_sweeper_job")
def approval_deadline_sweeper_job(tenant_slug: str | None = None) -> dict[str, str]:
    return {"status": "ok", "tenant_slug": tenant_slug or "*"}


@celery_app.task(name="send_edo_job")
def send_edo_job(*, message_id: str, tenant_id: str, provider_code: str) -> dict[str, str]:
    return {"status": "sent", "message_id": message_id, "tenant_id": tenant_id, "provider_code": provider_code}


@celery_app.task(name="edo_status_simulation_job")
def edo_status_simulation_job(*, message_id: str, tenant_id: str, status: str) -> dict[str, str]:
    async def _run() -> dict[str, str]:
        from sqlalchemy import select

        async with session_scope(tenant=tenant_id) as session:
            message = await session.get(EdoMessage, message_id)
            if message is None:
                return {"status": "missing", "message_id": message_id}
            message.status = EdoStatus(status)
            session.add(
                EdoStatusHistory(
                    tenant_id=tenant_id,
                    edo_message_id=message.id,
                    status=message.status,
                    raw_payload_json={"simulation": True},
                )
            )
            await OutboxService(session).enqueue(
                tenant_id=tenant_id,
                event_type=EventType.EDO_STATUS_CHANGED.value,
                payload={"tenant_id": tenant_id, "event_id": f"edo-sim-{message.id}-{status}", "metadata": {"edo_message_id": message.id, "status": status}},
                idempotency_key=f"edo.status.sim:{message.id}:{status}",
            )
            await session.flush()
            return {"status": message.status.value, "message_id": message.id}

    return _run_coroutine(_run())


@celery_app.task(name="webhook_dispatch_job")
def webhook_dispatch_job(limit: int = 50, tenant_slug: str = "test") -> dict[str, int]:
    dispatched = dispatch_outbox_events(tenant_slug=tenant_slug)
    return {"dispatched": int(dispatched), "limit": int(limit)}
