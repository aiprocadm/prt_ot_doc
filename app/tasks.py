"""Celery worker tasks for background document processing."""

from __future__ import annotations

import asyncio
import binascii
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
from app.core.metrics import get_metrics
from app.core.tenant import tenant_context
from app.db import ensure_tenant_schema, session_scope
from app.domains.files import s3
from app.domains.files.utils import build_dated_prefix
from app.domains.templating.renderer import render_docx
from app.models.document import Document, DocumentStatus, DocumentVersion
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
from app.schemas.template import TemplateCreate
from app.services.audit import AuditService
from app.services.celery_app import celery_app
from app.services.file_storage import FileStorageService
from app.services.idempotency import IdempotencyService
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
) -> str:
    """Persist template metadata and register an active version for a tenant."""

    def decode_checksum() -> bytes:
        try:
            return binascii.unhexlify(checksum_hex)
        except binascii.Error as exc:  # pragma: no cover - validated by caller
            raise ValueError("checksum must be hex-encoded") from exc

    async def _run() -> str:
        payload = TemplateCreate(name=name, description=description, metadata=metadata or {})
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
        storage = FileStorageService.default()
        metrics = get_metrics()
        with tenant_context(tenant_slug):
            ensure_tenant_schema(tenant_slug)
            async with session_scope(tenant=tenant_slug) as session:
                run = await session.get(PipelineRun, run_id)
                if run is None:
                    raise ValueError("Pipeline run not found")

                metadata = dict(run.result_metadata or {})
                existing_document_id = metadata.get("document_id")
                if run.status is PipelineRunStatus.DONE and existing_document_id:
                    return str(existing_document_id)

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
                try:
                    rendered = render_docx(template_bytes, context_payload)
                except Exception:
                    metrics.observe_pipeline_stage(
                        stage="generate_docx",
                        status="error",
                        seconds=perf_counter() - docx_start,
                    )
                    raise
                metrics.observe_pipeline_stage(
                    stage="generate_docx",
                    status="success",
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
                    status=DocumentStatus.DRAFT,
                    created_by=user.id,
                )
                session.add(document)
                await session.flush()

                storage_key = f"{tenant_prefix}/documents/{document.id}/{uuid4().hex}.docx"
                upload_start = perf_counter()
                try:
                    s3.put_object(data=rendered, mime=DOCX_MIME, key=storage_key)
                except Exception:
                    metrics.observe_pipeline_stage(
                        stage="upload_s3",
                        status="error",
                        seconds=perf_counter() - upload_start,
                    )
                    raise
                metrics.observe_pipeline_stage(
                    stage="upload_s3",
                    status="success",
                    seconds=perf_counter() - upload_start,
                )
                document.storage_key = storage_key

                version = DocumentVersion(
                    document=document,
                    template_version=str(template_version.version),
                    data_json=context_payload,
                    file_key=storage_key,
                    template_version_id=template_version.id,
                )
                session.add(version)

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
                metrics.observe_pipeline_stage(
                    stage="stamp",
                    status="skipped",
                    seconds=0.0,
                )
                outbox = OutboxService(session)
                await outbox.enqueue(
                    tenant_id=run.tenant_id,
                    event_type="DocumentGenerated",
                    payload={
                        "document_id": document.id,
                        "document_version_id": version.id,
                        "template_id": template.id,
                        "template_version_id": template_version.id,
                        "company_id": company.id,
                        "person_id": person.id if person else None,
                        "storage_key": storage_key,
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
                return document.id

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
