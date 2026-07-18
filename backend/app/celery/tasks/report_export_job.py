"""Materializer for report-builder export jobs (P10-07 §24.3).

Зеркало ``audit_export_job.py``: ExportJob(export_type="report") → engine →
renderer → FileStorageService + File row → job.file_id/status. Скачивание —
выделенный GET /report-builder/exports/{job_id}/download (стримит из
FileStorageService напрямую, паттерн audit-экспорта: legacy
/files/{file_id}/download не работает для generated-ключей вне tenants/*).
PDF — печатный формат, не bulk: свой маленький кап PDF_ROW_CAP с отдельным
кодом ошибки (не путать с pdf_renderer_unavailable — ревью-фикс группы B).
"""

from __future__ import annotations

import hashlib
from typing import Any

from sqlalchemy import select

from app.core.tenant import tenant_context
from app.db.session import ensure_tenant_schema, session_scope
from app.db.tenant_row_guard import assert_tenant_row_matches_session
from app.models.file import File, FileKind, FileScanStatus
from app.models.report_builder import ReportDefinition
from app.modules.projections.models import ExportJob
from app.modules.report_builder.engine import (
    EXPORT_ROW_CAP,
    ReportConfigError,
    run_report,
)
from app.modules.report_builder.renderers import (
    CSV_MEDIA,
    PDF_MEDIA,
    XLSX_MEDIA,
    PdfRendererUnavailable,
    render_csv,
    render_pdf,
    render_xlsx,
)
from app.services.celery_app import celery_app
from app.services.file_storage import FileStorageService

PDF_ROW_CAP = 2_000

_FORMATS: dict[str, tuple[str, str]] = {
    "csv": (CSV_MEDIA, "csv"),
    "xlsx": (XLSX_MEDIA, "xlsx"),
    "pdf": (PDF_MEDIA, "pdf"),
}


@celery_app.task(name="app.tasks.report_export_job")
def report_export_job(*, job_id: str, tenant_id: str) -> dict[str, str]:
    from app.tasks import _run_coroutine

    async def _run() -> dict[str, str]:
        with tenant_context(tenant_id):
            ensure_tenant_schema(tenant_id)
            async with session_scope(tenant=tenant_id) as session:
                job = await session.get(ExportJob, job_id)
                if job is None or job.export_type != "report":
                    return {"status": "missing"}
                try:
                    assert_tenant_row_matches_session(
                        session,
                        job,
                        mismatch_event="report_export_job.tenant_scope_mismatch",
                        not_found_message="missing",
                    )
                except ValueError:
                    return {"status": "missing"}
                resolved = str(session.info.get("tenant_id") or "").strip() or tenant_id

                # Celery at-least-once redelivery guard: a re-run of a terminal job
                # must not create a second File row / overwrite file_id.
                if job.status in {"done", "failed"}:
                    return {"status": job.status}

                async def _fail(code: str, message: str) -> dict[str, str]:
                    job.status = "failed"
                    job.error_payload = {"code": code, "message": message}
                    await session.commit()
                    return {"status": "failed"}

                try:
                    job.status = "running"
                    await session.flush()

                    scope: dict[str, Any] = job.scope_json or {}
                    fmt = str(scope.get("format") or "")
                    if fmt not in _FORMATS:
                        return await _fail("format_unknown", f"Unknown export format: {fmt!r}")
                    definition = await session.scalar(
                        select(ReportDefinition).where(
                            ReportDefinition.id == str(scope.get("definition_id") or ""),
                            ReportDefinition.tenant_id == resolved,
                            ReportDefinition.deleted_at.is_(None),
                        )
                    )
                    if definition is None:
                        return await _fail("definition_missing", "Report definition was deleted")

                    try:
                        result = await run_report(
                            session,
                            tenant_id=resolved,
                            dataset_code=definition.dataset_code,
                            config=definition.config_json,
                            # PDF is capped far below EXPORT_ROW_CAP — no point pulling
                            # 50k rows only to reject them; total (a separate COUNT) is
                            # unaffected, so the cap checks below stay exact.
                            limit=PDF_ROW_CAP + 1 if fmt == "pdf" else EXPORT_ROW_CAP,
                        )
                    except ReportConfigError as exc:
                        return await _fail(exc.code, exc.message)
                    if result.total > EXPORT_ROW_CAP:
                        return await _fail(
                            "row_limit_exceeded",
                            f"Report yields {result.total} rows; the cap is {EXPORT_ROW_CAP}",
                        )
                    if fmt == "pdf" and result.total > PDF_ROW_CAP:
                        return await _fail(
                            "pdf_row_limit_exceeded",
                            f"PDF is a print format: {result.total} rows exceed the "
                            f"{PDF_ROW_CAP} cap; use CSV/XLSX or narrow the filters",
                        )

                    mime, ext = _FORMATS[fmt]
                    try:
                        if fmt == "csv":
                            body = render_csv(result)
                        elif fmt == "xlsx":
                            body = render_xlsx(result, title=definition.name)
                        else:
                            body = render_pdf(result, title=definition.name)
                    except PdfRendererUnavailable as exc:
                        return await _fail("pdf_renderer_unavailable", str(exc))

                    key = f"{resolved}/exports/reports/{job.id}.{ext}"
                    FileStorageService.default().put(key, body, content_type=mime)
                    file = File(
                        tenant_id=resolved,
                        storage_key=key,
                        bucket="generated",
                        sha256=hashlib.sha256(body).hexdigest(),
                        size=len(body),
                        mime=mime,
                        original_name=f"{definition.name}.{ext}",
                        kind=FileKind.DOCUMENT,
                        is_quarantined=False,
                        scan_status=FileScanStatus.CLEAN,
                        meta_json={"generated_by": "report_export_job"},
                    )
                    session.add(file)
                    await session.flush()
                    job.file_id = file.id
                    job.row_count = result.total
                    job.progress_percent = 100
                    job.status = "done"
                    await session.commit()
                    return {"status": "ok", "job_id": job_id}
                except Exception as exc:  # noqa: BLE001 — job must not stick in running/queued
                    # An untyped failure (sqlalchemy DataError/OperationalError from an
                    # arbitrary user config, openpyxl crash, storage.put outage) would
                    # otherwise bubble out of _run(), session_scope would roll the
                    # transaction back, the status="running" write would revert, and the
                    # job would poll as "queued" forever with error_payload=None.
                    await session.rollback()  # a DB error may have aborted the transaction
                    job2 = await session.get(ExportJob, job_id)
                    if job2 is not None:
                        job2.status = "failed"
                        job2.error_payload = {
                            "code": "internal_error",
                            "message": str(exc)[:500],
                        }
                        await session.commit()
                    return {"status": "failed"}

    return _run_coroutine(_run())


__all__ = ["report_export_job"]
