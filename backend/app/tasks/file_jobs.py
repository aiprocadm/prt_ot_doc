"""File & PDF Celery jobs — extracted from _core.py (ARCH-4 decomposition).

Pure move: identical task definitions, explicit ``name=`` preserved, so Celery
registration is unchanged. Re-exported from ``_core`` for back-compat
(``from app.tasks import apply_headers_job`` etc., and the thin wrappers in
``app.celery.tasks.*`` that import from ``app.tasks``).

Covers header application, DOCX→PDF conversion, file-content indexing and the
AV-scan delegate. Depends only on the leaf module ``app.tasks._shared`` — never
imports back into ``_core`` — so there is no cycle. Heavy third-party imports
(LibreOffice pool, pdf converters) stay function-local as in the original.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone

from sqlalchemy import select

from app.core.tenant import tenant_context
from app.db import ensure_tenant_schema, session_scope
from app.db.tenant_row_guard import (
    assert_tenant_row_matches_session as _assert_tenant_row_matches_session,
)
from app.models.document import DocumentVersion
from app.models.job_engine import (
    DocumentArtifact,
    DocumentJob,
    DocumentJobStatus,
    DocumentJobStep,
    JobStepStatus,
)
from app.models.models import Tenant
from app.modules.headers.engine import apply_headers_to_docx
from app.modules.headers.repo import get_preset_by_code
from app.services.celery_app import celery_app
from app.services.file_storage import FileStorageService
from app.tasks._shared import DOCX_MIME, RETRYABLE_EXCEPTIONS, _run_coroutine

logger = logging.getLogger(__name__)


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
                _assert_tenant_row_matches_session(
                    session,
                    job,
                    mismatch_event="document_job.tenant_scope_mismatch",
                    not_found_message="Job not found",
                )
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
                _assert_tenant_row_matches_session(
                    session,
                    version,
                    mismatch_event="document_version.tenant_scope_mismatch",
                    not_found_message="Document version not found",
                )
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
def convert_pdf_job(
    *,
    tenant_id: str,
    input_file_id: str,
    pdf_run_id: str,
    options: dict,
    correlation_id: str | None = None,
) -> dict[str, object]:
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
                try:
                    _assert_tenant_row_matches_session(
                        session,
                        run,
                        mismatch_event="pdf_conversion_run.tenant_scope_mismatch",
                        not_found_message="missing_run",
                    )
                except ValueError:
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
                        try:
                            _assert_tenant_row_matches_session(
                                session,
                                run,
                                mismatch_event="pdf_conversion_run.tenant_scope_mismatch",
                                not_found_message="missing_input",
                            )
                            _assert_tenant_row_matches_session(
                                session,
                                source,
                                mismatch_event="file.tenant_scope_mismatch",
                                not_found_message="missing_input",
                            )
                        except ValueError:
                            return {"status": "missing_input"}

                        source_bytes = load_source_bytes(source)
                        pdf_bytes, sha256_hex = convert_docx_bytes(
                            source_bytes=source_bytes, timeout_s=timeout_s, pool=pool
                        )

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
                        index_file_content_job.apply_async(
                            kwargs={"tenant_slug": tenant_id, "file_id": existing.id}, countdown=0
                        )
                        return {
                            "status": "success",
                            "output_file_id": existing.id,
                            "attempts": attempts,
                        }
                except Exception as exc:  # noqa: BLE001
                    last_error = exc
                    logger.exception(
                        "pdf.convert.failed",
                        extra={"attempt": attempts, "correlation_id": correlation_id},
                    )

            async with session_scope(tenant=tenant_id) as session:
                run = await session.get(PdfConversionRun, pdf_run_id)
                if run is not None:
                    try:
                        _assert_tenant_row_matches_session(
                            session,
                            run,
                            mismatch_event="pdf_conversion_run.tenant_scope_mismatch",
                            not_found_message="missing_run",
                        )
                    except ValueError:
                        pass
                    else:
                        run.attempts = attempts
                        run.status = PdfRunStatus.FAILED.value
                        run.ended_at = datetime.now(timezone.utc)
                        run.error_code = (
                            map_failure(last_error) if last_error else "PDF_CONVERSION_FAILED"
                        )
                        run.error_payload = {"error": str(last_error)[:500]} if last_error else {}
                        await session.flush()
            return {"status": "failed", "attempts": attempts}

    return _run_coroutine(_run())


@celery_app.task(name="files.index_content", bind=True, max_retries=3, default_retry_delay=30)
def index_file_content_job(
    self, tenant_slug: str, version_id: str | None = None, file_id: str | None = None
):
    async def _run() -> dict[str, str]:
        from app.modules.files.service import index_file_record, index_file_version

        with tenant_context(tenant_slug):
            ensure_tenant_schema(tenant_slug)
            async with session_scope(tenant=tenant_slug) as session:
                tenant_id = str(session.info.get("tenant_id") or "")
                if not tenant_id:
                    tenant = (
                        await session.execute(select(Tenant).where(Tenant.slug == tenant_slug))
                    ).scalar_one_or_none()
                    if tenant is None:
                        return {"status": "tenant_missing"}
                    tenant_id = str(tenant.id)
                if version_id:
                    await index_file_version(session, tenant_id=tenant_id, version_id=version_id)
                if file_id:
                    await index_file_record(session, tenant_id=tenant_id, file_id=file_id)
                await session.flush()
                # Срез-158. Отсюда уходило событие «edo.status_changed» с
                # пометкой «FileIndexed» — обратный адрес был чужой. В ЭДО
                # ничего не происходило: индексация просто раскладывает
                # содержимое файла для поиска. Правило «когда изменился статус
                # в ЭДО» срабатывало на это и молчало на настоящую смену
                # статуса — её теперь публикует обработчик вебхука оператора
                # (``app/tasks/_core.py``). Своего события у индексации нет и
                # не заводим: подписчиков у неё не было.
                return {"status": "ok", "version_id": version_id or "", "file_id": file_id or ""}

    try:
        return _run_coroutine(_run())
    except RETRYABLE_EXCEPTIONS as exc:
        raise self.retry(exc=exc)


@celery_app.task(name="files.av_scan_file_job")
def av_scan_file_job(tenant_id: str, file_id: str) -> str:
    from app.modules.files.tasks import av_scan_file_job as _delegate

    return _delegate(tenant_id, file_id)
