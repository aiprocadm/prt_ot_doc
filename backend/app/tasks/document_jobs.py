"""Document-generation Celery tasks — extracted from _core.py (ARCH-4 decomposition).

Pure move: identical task definitions, explicit ``name=`` preserved, so Celery
registration is unchanged. Re-exported from ``_core`` for back-compat
(``from app.tasks._core import generate_document_task`` / ``from app.tasks import …``).

Covers template registration, single-run document render
(``_generate_document_for_run``) and batch-item processing. Depends only on the leaf
module ``app.tasks._shared`` — never imports back into ``_core`` — so there is no cycle.
"""

from __future__ import annotations

import binascii
import hashlib
import logging
from datetime import datetime, timezone
from time import perf_counter
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.metrics import PipelineStage, PipelineType, StageResult, get_metrics
from app.core.payload_constraints import normalize_output_basename
from app.core.tenant import tenant_context
from app.db import ensure_tenant_schema, session_scope
from app.db.tenant_row_guard import (
    assert_tenant_row_matches_session as _assert_tenant_row_matches_session,
)
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
from app.modules.branding.letterhead import LetterheadResolver
from app.modules.branding.schemas import IssuerRef, LetterheadOverride
from app.modules.branding.service import BrandingService
from app.modules.headers.engine import apply_headers_to_docx
from app.modules.templates.passport import inject_passport
from app.modules.templates.service import build_passport
from app.repository import create_template
from app.schemas.template import TemplateCreate, TemplateVersionMetadata
from app.services.audit import AuditService
from app.services.celery_app import celery_app
from app.services.document_orchestration import normalize_user_facing_error, set_state
from app.services.events import EventType
from app.services.file_storage import FileStorageService
from app.services.idempotency import IdempotencyService
from app.services.outbox import OutboxService
from app.tasks._shared import DOCX_MIME, RETRYABLE_EXCEPTIONS, _run_coroutine

settings = get_settings()
logger = logging.getLogger(__name__)


def _assert_pipeline_run_matches_session_tenant(session: AsyncSession, run: PipelineRun) -> None:
    _assert_tenant_row_matches_session(
        session,
        run,
        mismatch_event="pipeline.run.tenant_scope_mismatch",
        not_found_message="Pipeline run not found",
    )


def _assert_batch_item_scope(
    session: AsyncSession,
    batch: DocumentBatchRun | None,
    item: DocumentBatchItem | None,
    *,
    batch_id: str,
    item_id: str,
) -> None:
    if batch is None or item is None:
        raise ValueError("Batch item not found")
    _assert_tenant_row_matches_session(
        session,
        batch,
        mismatch_event="document.batch_run.tenant_scope_mismatch",
        not_found_message="Batch item not found",
    )
    _assert_tenant_row_matches_session(
        session,
        item,
        mismatch_event="document.batch_item.tenant_scope_mismatch",
        not_found_message="Batch item not found",
    )
    if str(item.batch_id) != str(batch.id):
        logger.warning(
            "document.batch_item.parent_mismatch",
            extra={
                "batch_id": batch_id,
                "item_id": item_id,
                "item_batch_id": item.batch_id,
                "batch_row_id": batch.id,
            },
        )
        raise ValueError("Batch item not found")


async def _generate_document_for_run(run_id: str, tenant_slug: str) -> tuple[str, str]:
    storage = FileStorageService.default()
    metrics = get_metrics()
    pipeline_start = perf_counter()
    metrics.increment_pipeline_inflight(pipeline=PipelineType.DOCUMENT)
    with tenant_context(tenant_slug):
        ensure_tenant_schema(tenant_slug)
        logger.info(
            "tasks.pipeline.document_generate.start",
            extra={"tenant_slug": tenant_slug, "pipeline_run_id": run_id},
        )
        async with session_scope(tenant=tenant_slug) as session:
            try:
                run = await session.get(PipelineRun, run_id)
                if run is None:
                    raise ValueError("Pipeline run not found")
                _assert_pipeline_run_matches_session_tenant(session, run)

                metadata = dict(run.result_metadata or {})
                metadata["orchestration"] = set_state(
                    metadata.get("orchestration"), state="generated"
                )
                existing_document_id = metadata.get("document_id")
                existing_version_id = metadata.get("document_version_id")
                if run.status == PipelineRunStatus.DONE and existing_document_id:
                    return str(existing_document_id), str(existing_version_id or "")

                company_id = metadata.get("company_id")
                person_id = metadata.get("person_id")
                initiated_by = metadata.get("initiated_by")

                if not company_id or not initiated_by:
                    raise ValueError("Pipeline run metadata is incomplete")

                template_version = await session.get(TemplateVersion, run.template_version_id)
                if template_version is None:
                    raise ValueError("Template version not found")
                _assert_tenant_row_matches_session(
                    session,
                    template_version,
                    mismatch_event="template_version.tenant_scope_mismatch",
                    not_found_message="Template version not found",
                )
                if not template_version.payload_key:
                    raise ValueError("Template version payload is missing")

                template = await session.get(Template, run.template_id)
                if template is None:
                    raise ValueError("Template not found")
                _assert_tenant_row_matches_session(
                    session,
                    template,
                    mismatch_event="template.tenant_scope_mismatch",
                    not_found_message="Template not found",
                )

                company = await session.get(Company, company_id)
                if company is None:
                    raise ValueError("Company not found")
                _assert_tenant_row_matches_session(
                    session,
                    company,
                    mismatch_event="company.tenant_scope_mismatch",
                    not_found_message="Company not found",
                )

                person = None
                if person_id is not None:
                    person = await session.get(Person, person_id)
                    if person is None:
                        raise ValueError("Person not found")
                    _assert_tenant_row_matches_session(
                        session,
                        person,
                        mismatch_event="person.tenant_scope_mismatch",
                        not_found_message="Person not found",
                    )
                    if person.company_id != company.id:
                        raise ValueError("Person does not belong to company")

                user = await session.get(User, initiated_by)
                if user is None:
                    raise ValueError("Initiating user not found")
                _assert_tenant_row_matches_session(
                    session,
                    user,
                    mismatch_event="user.tenant_scope_mismatch",
                    not_found_message="Initiating user not found",
                )

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
                    tenant_id=run.tenant_id,
                    generated_by=(user.email or user.id),
                    correlation_id=correlation_id,
                    data=context_payload,
                    options={"visible_passport": True},
                    npa_binding_id=(
                        str(metadata.get("npa_binding_id"))
                        if metadata.get("npa_binding_id")
                        else None
                    ),
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
                    letterhead_decision = None
                    if settings.doc_pipeline_letterhead_auto:
                        tenant = await session.get(Tenant, run.tenant_id)
                        if tenant is None:
                            raise ValueError("Tenant not found for letterhead resolution")
                        raw_letterhead = metadata.get("letterhead") or (run.context or {}).get(
                            "letterhead"
                        )
                        override = (
                            LetterheadOverride.model_validate(raw_letterhead)
                            if raw_letterhead
                            else None
                        )
                        issuer = (
                            override.issuer
                            if override is not None and override.issuer is not None
                            else IssuerRef(kind="company", company_id=company.id)
                        )
                        resolver = LetterheadResolver(BrandingService(session, tenant))
                        letterhead_decision = await resolver.resolve(
                            issuer=issuer,
                            site_id=metadata.get("site_id") or (run.context or {}).get("site_id"),
                            doc={"title": template.name, "generated_at": now.isoformat()},
                            override=override,
                        )
                    if letterhead_decision is not None and letterhead_decision.apply:
                        rendered_base, _report = apply_headers_to_docx(
                            docx_bytes=rendered_base,
                            preset=letterhead_decision.preset,
                            context=letterhead_decision.header_context,
                            watermark_override=letterhead_decision.watermark,
                        )
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
                        "letterhead": (
                            letterhead_decision.as_render_log()
                            if letterhead_decision
                            else {"applied": False}
                        ),
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
                    data_json={
                        **context_payload,
                        "passport": passport,
                        "correlation_id": correlation_id,
                    },
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
                metadata["orchestration"] = set_state(
                    metadata.get("orchestration"), state="headers_applied"
                )
                metadata["orchestration"] = set_state(
                    metadata.get("orchestration"), state="pdf_ready"
                )
                metadata["orchestration"] = set_state(
                    metadata.get("orchestration"), state="handoff_ready"
                )

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
    bind=True,
    name="app.tasks.generate_document",
    autoretry_for=RETRYABLE_EXCEPTIONS,
    retry_backoff=settings.celery.retry_backoff_seconds,
    retry_backoff_max=settings.celery.retry_backoff_max_seconds,
    retry_jitter=True,
    retry_kwargs={"max_retries": settings.celery.task_max_retries},
)
def generate_document_task(self, run_id: str, *, tenant_slug: str) -> str:
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
                        _assert_pipeline_run_matches_session_tenant(session, run)
                        retries = int(getattr(self.request, "retries", 0) or 0)
                        max_retries = int(settings.celery.task_max_retries)
                        is_retrying = retries < max_retries
                        metadata = dict(run.result_metadata or {})
                        next_state = "retrying" if is_retrying else "failed"
                        details = {"attempt": retries + 1, "error": str(exception)[:255]}
                        metadata["orchestration"] = set_state(
                            metadata.get("orchestration"), state=next_state, details=details
                        )
                        metadata["user_facing_error"] = normalize_user_facing_error(str(exception))
                        run.result_metadata = metadata
                        run.error = str(exception)[:255]
                        run.status = (
                            PipelineRunStatus.QUEUED if is_retrying else PipelineRunStatus.ERROR
                        )
                        run.finished_at = None if is_retrying else datetime.now(tz=timezone.utc)
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
                            details={
                                "status": next_state,
                                "error": str(exception)[:255],
                                "attempt": retries + 1,
                            },
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
                _assert_batch_item_scope(session, batch, item, batch_id=batch_id, item_id=item_id)
                if item.status == DocumentBatchItemStatus.SUCCEEDED:
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
                _assert_batch_item_scope(session, batch, item, batch_id=batch_id, item_id=item_id)

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
        try:
            _assert_batch_item_scope(session, batch, item, batch_id=batch_id, item_id=item_id)
        except ValueError:
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
