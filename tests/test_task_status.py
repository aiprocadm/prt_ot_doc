import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.models import (
    PipelineRun,
    PipelineRunStatus,
    Template,
    TemplateVersion,
    TemplateVersionStatus,
    Tenant,
)


@pytest.mark.anyio
async def test_task_status_endpoint(async_client: AsyncClient, sessionmaker, make_auth_headers) -> None:
    async with sessionmaker() as session:
        tenant = (
            await session.execute(select(Tenant).where(Tenant.slug == "test"))
        ).scalar_one()
        session.info["tenant"] = tenant.slug

        template = Template(
            tenant_id=tenant.id,
            name="REPORT",
            description="",
            metadata_json={},
            storage_key="templates/report.docx",
        )
        session.add(template)
        await session.flush()

        version = TemplateVersion(
            tenant_id=tenant.id,
            template_id=template.id,
            version=1,
            checksum=b"checksum",
            status=TemplateVersionStatus.ACTIVE,
            payload_key="templates/report.docx",
        )
        session.add(version)
        await session.flush()

        run = PipelineRun(
            tenant_id=tenant.id,
            template_id=template.id,
            template_version_id=version.id,
            status=PipelineRunStatus.DONE,
            context={"foo": "bar"},
            outputs={"document_id": "doc-123"},
            result_metadata={"document_id": "doc-123", "note": "complete"},
            idempotency_key="status-test",
        )
        session.add(run)
        await session.commit()
        run_id = run.id

    headers = await make_auth_headers()
    response = await async_client.get(f"/api/v1/tasks/{run_id}", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["task_id"] == run_id
    assert body["status"] == PipelineRunStatus.DONE.value
    assert body["document_id"] == "doc-123"
    assert body["metadata"]["note"] == "complete"
    assert body["metadata"]["outputs"]["document_id"] == "doc-123"


@pytest.mark.anyio
async def test_task_status_not_found(async_client: AsyncClient, make_auth_headers) -> None:
    headers = await make_auth_headers()
    response = await async_client.get(
        f"/api/v1/tasks/{uuid.uuid4()}", headers=headers
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "PENDING"
    assert body["metadata"].get("celery_status") == "PENDING"


@pytest.mark.anyio
async def test_tasks_list_etag_returns_304_on_if_none_match(
    async_client: AsyncClient, sessionmaker, make_auth_headers
) -> None:
    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        session.info["tenant"] = tenant.slug
        template = Template(
            tenant_id=tenant.id,
            name="TASK-ETAG",
            description="",
            metadata_json={},
            storage_key="templates/task-etag.docx",
        )
        session.add(template)
        await session.flush()
        version = TemplateVersion(
            tenant_id=tenant.id,
            template_id=template.id,
            version=1,
            checksum=b"checksum",
            status=TemplateVersionStatus.ACTIVE,
            payload_key="templates/task-etag.docx",
        )
        session.add(version)
        await session.flush()
        run = PipelineRun(
            tenant_id=tenant.id,
            template_id=template.id,
            template_version_id=version.id,
            status=PipelineRunStatus.QUEUED,
            context={},
            idempotency_key="tasks-list-etag",
        )
        session.add(run)
        await session.commit()

    headers = await make_auth_headers()
    first = await async_client.get("/api/v1/tasks", headers=headers)
    assert first.status_code == 200
    etag = first.headers.get("ETag")
    assert etag

    second = await async_client.get("/api/v1/tasks", headers={**headers, "If-None-Match": etag})
    assert second.status_code == 304
    assert second.headers.get("ETag") == etag
