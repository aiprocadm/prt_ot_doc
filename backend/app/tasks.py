"""Celery worker tasks for background document processing."""

from __future__ import annotations

import asyncio
import binascii
import hashlib
import logging
import threading
from datetime import datetime, timezone
from time import perf_counter
from typing import Any, Coroutine, TypeVar
from uuid import uuid4

from botocore.exceptions import ClientError
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.config import get_settings
from app.core.metrics import PipelineStage, PipelineType, StageResult, get_metrics
from app.core.payload_constraints import normalize_output_basename
from app.core.tenant import tenant_context
from app.db import AsyncSessionLocal, ensure_tenant_schema, session_scope
from app.domains.files import s3
from app.domains.files.utils import build_dated_prefix
from app.domains.templating.renderer import render_docx
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
    Person,
    PipelineRun,
    PipelineRunStatus,
    Template,
    TemplateVersion,
    Tenant,
    User,
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
                docx_start = perf_counter()
                metrics.record_pipeline_stage_start(
                    pipeline=PipelineType.DOCUMENT,
                    stage=PipelineStage.DOCX_GENERATED,
                )
                try:
                    rendered = render_docx(template_bytes, context_payload)
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
                    data_json=context_payload,
                    file_key=storage_key,
                    template_version_id=template_version.id,
                    snapshot_id=snapshot.id,
                )
                session.add(version)
                await session.flush()

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
def dispatch_outbox_events(max_attempts: int = 3) -> int:
    return _run_coroutine(_dispatch_outbox_events(max_attempts=max_attempts))


async def _dispatch_outbox_events(*, max_attempts: int = 3) -> int:
    processed = 0
    async with session_scope(tenant="test") as session:
        pending = (
            await session.execute(select(OutboxEvent).where(OutboxEvent.status == OutboxEventStatus.PENDING.value))
        ).scalars().all()
        for event in pending:
            event.attempts += 1
            if event.attempts > max_attempts:
                event.status = OutboxEventStatus.FAILED.value
                continue
            event.status = OutboxEventStatus.SENT.value
            processed += 1
        await session.flush()
    return processed


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
        from datetime import datetime, timezone
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
