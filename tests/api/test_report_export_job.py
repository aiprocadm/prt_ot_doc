"""Materializer: ExportJob(report) → file in storage + File row + job done/failed."""

from __future__ import annotations

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import select

from app.models.models import RoleEnum
from tests.utils.factories import TestDataFactory

BASE = "/api/v1/report-builder"


async def _setup(sessionmaker, data_factory: TestDataFactory) -> str:
    from app.models.feature import Feature, FeatureEnablement

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        feature = (
            await session.execute(select(Feature).where(Feature.code == "report_builder"))
        ).scalar_one_or_none()
        if feature is None:
            feature = Feature(code="report_builder", title="Конструктор отчётов")
            session.add(feature)
            await session.flush()
        session.add(FeatureEnablement(tenant_id=str(tenant.id), feature_id=feature.id, on=True))
        await session.commit()
        return str(tenant.id)


async def _create_definition(async_client, headers) -> str:
    resp = await async_client.post(
        f"{BASE}/definitions",
        json={
            "name": "Инциденты CSV",
            "dataset_code": "incidents",
            "config_json": {"columns": ["title", "status"]},
        },
        headers=headers,
    )
    assert resp.status_code == status.HTTP_201_CREATED, resp.text
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_run_creates_queued_job(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory, monkeypatch
):
    calls: list[dict] = []
    monkeypatch.setattr(
        "app.celery.tasks.report_export_job.report_export_job.delay",
        lambda **kw: calls.append(kw),
    )
    await _setup(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)
    definition_id = await _create_definition(async_client, headers)

    resp = await async_client.post(
        f"{BASE}/definitions/{definition_id}/run", json={"format": "csv"}, headers=headers
    )
    assert resp.status_code == status.HTTP_201_CREATED, resp.text
    body = resp.json()
    assert body["status"] == "queued"
    assert calls and calls[0]["job_id"] == body["job_id"]

    bad = await async_client.post(
        f"{BASE}/definitions/{definition_id}/run", json={"format": "docx"}, headers=headers
    )
    assert bad.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY  # Literal формат


@pytest.mark.asyncio
async def test_materializer_csv_end_to_end(
    async_client, make_auth_headers, sessionmaker, data_factory, monkeypatch
):
    from app.celery.tasks.report_export_job import report_export_job
    from app.models.file import File
    from app.modules.projections.models import ExportJob
    from app.services.file_storage import FileStorageService

    monkeypatch.setattr(
        "app.celery.tasks.report_export_job.report_export_job.delay", lambda **kw: None
    )
    tenant_id = await _setup(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)
    definition_id = await _create_definition(async_client, headers)
    run = await async_client.post(
        f"{BASE}/definitions/{definition_id}/run", json={"format": "csv"}, headers=headers
    )
    job_id = run.json()["job_id"]

    outcome = report_export_job(job_id=job_id, tenant_id=tenant_id)
    assert outcome["status"] == "ok"

    async with sessionmaker() as session:
        job = await session.get(ExportJob, job_id)
        assert job.status == "done"
        assert job.row_count == 0  # пустой тенант — но файл с заголовком есть
        assert job.file_id
        file = await session.get(File, job.file_id)
        assert file is not None and file.mime == "text/csv"
        content = FileStorageService.default().get(file.storage_key).decode("utf-8")
        assert "Название;Статус" in content


@pytest.mark.asyncio
async def test_materializer_failure_paths(
    async_client, make_auth_headers, sessionmaker, data_factory, monkeypatch
):
    from app.celery.tasks.report_export_job import report_export_job
    from app.modules.projections.models import ExportJob

    monkeypatch.setattr(
        "app.celery.tasks.report_export_job.report_export_job.delay", lambda **kw: None
    )
    tenant_id = await _setup(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)
    definition_id = await _create_definition(async_client, headers)
    run = await async_client.post(
        f"{BASE}/definitions/{definition_id}/run", json={"format": "pdf"}, headers=headers
    )
    job_id = run.json()["job_id"]

    # 1) отсутствующая definition → failed(definition_missing)
    async with sessionmaker() as session:
        from datetime import datetime, timezone

        from app.models.report_builder import ReportDefinition

        record = await session.get(ReportDefinition, definition_id)
        record.deleted_at = datetime.now(tz=timezone.utc)
        await session.commit()
    outcome = report_export_job(job_id=job_id, tenant_id=tenant_id)
    assert outcome["status"] == "failed"
    async with sessionmaker() as session:
        job = await session.get(ExportJob, job_id)
        assert job.status == "failed"
        assert job.error_payload["code"] == "definition_missing"
        # 2) вернуть definition, сломать PDF → pdf_renderer_unavailable
        record = await session.get(ReportDefinition, definition_id)
        record.deleted_at = None
        job.status = "queued"
        job.error_payload = None
        await session.commit()

    def _no_pdf(result, *, title):
        from app.modules.report_builder.renderers import PdfRendererUnavailable

        raise PdfRendererUnavailable("no soffice")

    monkeypatch.setattr("app.celery.tasks.report_export_job.render_pdf", _no_pdf)
    outcome = report_export_job(job_id=job_id, tenant_id=tenant_id)
    assert outcome["status"] == "failed"
    async with sessionmaker() as session:
        job = await session.get(ExportJob, job_id)
        assert job.error_payload["code"] == "pdf_renderer_unavailable"


@pytest.mark.asyncio
async def test_pdf_row_cap(
    async_client, make_auth_headers, sessionmaker, data_factory, monkeypatch
):
    """PDF — печатный формат: total > PDF_ROW_CAP → failed(pdf_row_limit_exceeded),
    БЕЗ попытки конвертации (не путать с pdf_renderer_unavailable)."""
    import app.celery.tasks.report_export_job as job_module
    from app.celery.tasks.report_export_job import report_export_job
    from app.modules.projections.models import ExportJob

    monkeypatch.setattr(
        "app.celery.tasks.report_export_job.report_export_job.delay", lambda **kw: None
    )
    tenant_id = await _setup(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)
    definition_id = await _create_definition(async_client, headers)
    run = await async_client.post(
        f"{BASE}/definitions/{definition_id}/run", json={"format": "pdf"}, headers=headers
    )
    job_id = run.json()["job_id"]

    monkeypatch.setattr(job_module, "PDF_ROW_CAP", -1)  # пустой тенант: total(0) > -1 → перекап

    def _boom(result, *, title):
        raise AssertionError("render_pdf must not be called when over cap")

    monkeypatch.setattr(job_module, "render_pdf", _boom)
    outcome = report_export_job(job_id=job_id, tenant_id=tenant_id)
    assert outcome["status"] == "failed"
    async with sessionmaker() as session:
        job = await session.get(ExportJob, job_id)
        assert job.error_payload["code"] == "pdf_row_limit_exceeded"


@pytest.mark.asyncio
async def test_materializer_unexpected_error_fails_job(
    async_client, make_auth_headers, sessionmaker, data_factory, monkeypatch
):
    """Нетипизированное исключение НЕ должно оставить job в running/queued навсегда:
    broad handler переводит его в failed(internal_error)."""
    from app.celery.tasks.report_export_job import report_export_job
    from app.modules.projections.models import ExportJob

    monkeypatch.setattr(
        "app.celery.tasks.report_export_job.report_export_job.delay", lambda **kw: None
    )
    tenant_id = await _setup(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)
    definition_id = await _create_definition(async_client, headers)
    run = await async_client.post(
        f"{BASE}/definitions/{definition_id}/run", json={"format": "csv"}, headers=headers
    )
    job_id = run.json()["job_id"]

    def _boom(result):
        raise RuntimeError("boom")

    monkeypatch.setattr("app.celery.tasks.report_export_job.render_csv", _boom)
    outcome = report_export_job(job_id=job_id, tenant_id=tenant_id)
    assert outcome["status"] == "failed"
    async with sessionmaker() as session:
        job = await session.get(ExportJob, job_id)
        assert job.status == "failed"
        assert job.error_payload["code"] == "internal_error"
        assert "boom" in job.error_payload["message"]


@pytest.mark.asyncio
async def test_materializer_skips_terminal_job(
    async_client, make_auth_headers, sessionmaker, data_factory, monkeypatch
):
    """Celery at-least-once redelivery: повторный прогон done-job не создаёт
    вторую File-строку и не переписывает file_id."""
    from sqlalchemy import func, select

    from app.celery.tasks.report_export_job import report_export_job
    from app.models.file import File
    from app.modules.projections.models import ExportJob

    monkeypatch.setattr(
        "app.celery.tasks.report_export_job.report_export_job.delay", lambda **kw: None
    )
    tenant_id = await _setup(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)
    definition_id = await _create_definition(async_client, headers)
    run = await async_client.post(
        f"{BASE}/definitions/{definition_id}/run", json={"format": "csv"}, headers=headers
    )
    job_id = run.json()["job_id"]

    outcome = report_export_job(job_id=job_id, tenant_id=tenant_id)
    assert outcome["status"] == "ok"
    async with sessionmaker() as session:
        job = await session.get(ExportJob, job_id)
        first_file_id = job.file_id
        files_before = int(
            await session.scalar(
                select(func.count()).select_from(File).where(File.tenant_id == tenant_id)
            )
            or 0
        )

    redelivered = report_export_job(job_id=job_id, tenant_id=tenant_id)
    assert redelivered == {"status": "done"}
    async with sessionmaker() as session:
        job = await session.get(ExportJob, job_id)
        assert job.status == "done"
        assert job.file_id == first_file_id
        files_after = int(
            await session.scalar(
                select(func.count()).select_from(File).where(File.tenant_id == tenant_id)
            )
            or 0
        )
        assert files_after == files_before


@pytest.mark.asyncio
async def test_download_endpoint(
    async_client, make_auth_headers, sessionmaker, data_factory, monkeypatch
):
    """End-to-end скачивание через выделенный роут (legacy /files/{id}/download
    не работает для generated-ключей): 409 до материализации, 200 после,
    404 для несуществующего job_id."""
    from uuid import uuid4

    from app.celery.tasks.report_export_job import report_export_job

    monkeypatch.setattr(
        "app.celery.tasks.report_export_job.report_export_job.delay", lambda **kw: None
    )
    tenant_id = await _setup(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)
    definition_id = await _create_definition(async_client, headers)
    run = await async_client.post(
        f"{BASE}/definitions/{definition_id}/run", json={"format": "csv"}, headers=headers
    )
    job_id = run.json()["job_id"]

    not_ready = await async_client.get(f"{BASE}/exports/{job_id}/download", headers=headers)
    assert not_ready.status_code == status.HTTP_409_CONFLICT

    outcome = report_export_job(job_id=job_id, tenant_id=tenant_id)
    assert outcome["status"] == "ok"

    resp = await async_client.get(f"{BASE}/exports/{job_id}/download", headers=headers)
    assert resp.status_code == status.HTTP_200_OK, resp.text
    assert resp.headers["content-type"].startswith("text/csv")
    assert "attachment" in resp.headers["content-disposition"]
    assert "Название;Статус" in resp.text

    missing = await async_client.get(f"{BASE}/exports/{uuid4()}/download", headers=headers)
    assert missing.status_code == status.HTTP_404_NOT_FOUND
