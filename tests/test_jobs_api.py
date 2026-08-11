from __future__ import annotations

import pytest
from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.middleware.tenant import TenantMiddleware
from app.models.job_engine import DocumentJob, DocumentJobStatus, DocumentJobStep, JobStepStatus
from app.models.models import Tenant
from app.modules.files.models import FileRecord, FileStatus


async def _ensure_global_tenant(*, slug: str = "test", tenant_id: str | None = None) -> None:
    async with AsyncSessionLocal(
        tenant="public", include_public=False, create_schema=False
    ) as session:
        existing = (
            await session.execute(select(Tenant).where(Tenant.slug == slug))
        ).scalar_one_or_none()
        if existing is not None:
            return
        payload = {"slug": slug, "name": slug.title(), "contact_email": f"{slug}@example.com"}
        if tenant_id is not None:
            payload["id"] = tenant_id
        session.add(Tenant(**payload))
        await session.commit()


@pytest.fixture(autouse=True)
def _bypass_tenant_middleware(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _dispatch_passthrough(self, request, call_next):  # type: ignore[no-untyped-def]
        return await call_next(request)

    monkeypatch.setattr(TenantMiddleware, "dispatch", _dispatch_passthrough)


@pytest.mark.anyio
async def test_job_status_endpoint_for_unknown_job(
    async_client, make_auth_headers, sessionmaker, data_factory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
    await _ensure_global_tenant(slug=tenant.slug, tenant_id=str(tenant.id))
    headers = await make_auth_headers()
    headers["x-tenant"] = str(tenant.id)
    response = await async_client.get("/api/v1/jobs/unknown", headers=headers)

    assert response.status_code == 404


@pytest.mark.anyio
async def test_jobs_list_and_retry_step_endpoints(
    async_client,
    make_auth_headers,
    sessionmaker,
    data_factory,
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        job = DocumentJob(
            tenant_id=str(tenant.id),
            kind="pipeline",
            status=DocumentJobStatus.FAILED.value,
            pipeline_profile_id=None,
            preset_id=None,
            input_sha256="a" * 64,
            request_hash="b" * 64,
            idempotency_key="idem-job-test",
            template_code="TMP",
            template_version=1,
            correlation_id="corr-1",
            created_by="user-1",
            error_code="step_failed",
            error_payload={"step": "convert_pdf"},
        )
        session.add(job)
        await session.flush()
        session.add(
            DocumentJobStep(
                tenant_id=str(tenant.id),
                job_id=job.id,
                step_code="convert_pdf",
                status=JobStepStatus.FAILED.value,
                attempts=1,
                input_ref={"job_id": job.id},
                error_code="step_failed",
                error_payload={"step": "convert_pdf"},
            )
        )
        await session.commit()
        job_id = job.id

    headers = await make_auth_headers()
    headers["x-tenant"] = str(tenant.id)
    await _ensure_global_tenant(slug=tenant.slug, tenant_id=str(tenant.id))
    listed = await async_client.get("/api/v1/jobs", headers=headers)
    assert listed.status_code == 200, listed.text
    payload = listed.json()
    assert any(item["id"] == job_id for item in payload["items"])

    retried = await async_client.post(
        f"/api/v1/jobs/{job_id}:retry-step",
        json={"step_key": "convert_pdf"},
        headers=headers,
    )
    assert retried.status_code == 200
    body = retried.json()
    assert body["job"]["id"] == job_id
    assert body["job"]["status"] in {
        DocumentJobStatus.RUNNING.value,
        DocumentJobStatus.SUCCESS.value,
        DocumentJobStatus.FAILED.value,
    }


@pytest.mark.anyio
async def test_create_job_endpoint_with_idempotency(
    async_client, make_auth_headers, sessionmaker, data_factory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
    await _ensure_global_tenant(slug=tenant.slug, tenant_id=str(tenant.id))
    headers = await make_auth_headers()
    headers["x-tenant"] = str(tenant.id)

    profile_payload = {
        "code": "jobs_default_v1",
        "name": "Jobs default",
        "steps": [{"code": "render_docx", "required": True, "params_schema": "RenderParamsV1"}],
        "limits": {"max_parallel": 2, "max_parallel_per_step": {}},
        "is_active": True,
    }
    created = await async_client.post(
        "/api/v1/pipelines/profiles", json=profile_payload, headers=headers
    )
    assert created.status_code == 201, created.text
    profile_id = created.json()["id"]

    payload = {"profile_id": profile_id, "inputs": {"x": 1}, "options": {"run_async": True}}
    resp1 = await async_client.post(
        "/api/v1/jobs", json=payload, headers={**headers, "Idempotency-Key": "job-create-idem"}
    )
    assert resp1.status_code == 202
    resp2 = await async_client.post(
        "/api/v1/jobs", json=payload, headers={**headers, "Idempotency-Key": "job-create-idem"}
    )
    assert resp2.status_code == 202
    assert resp1.json()["job_id"] == resp2.json()["job_id"]


@pytest.mark.anyio
async def test_jobs_cancel_and_retry_slash_endpoints(
    async_client, make_auth_headers, sessionmaker, data_factory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        job = DocumentJob(
            tenant_id=str(tenant.id),
            kind="pipeline",
            status=DocumentJobStatus.QUEUED.value,
            pipeline_profile_id=None,
            preset_id=None,
            input_sha256="a" * 64,
            request_hash="b" * 64,
            idempotency_key="idem-job-slash",
            template_code="TMP",
            template_version=1,
            correlation_id="corr-slash",
            created_by="user-1",
        )
        session.add(job)
        await session.flush()
        session.add(
            DocumentJobStep(
                tenant_id=str(tenant.id),
                job_id=job.id,
                step_code="render_docx",
                status=JobStepStatus.QUEUED.value,
                attempts=0,
                input_ref={"job_id": job.id},
            )
        )
        await session.commit()
        job_id = job.id

    headers = await make_auth_headers()
    headers["x-tenant"] = str(tenant.id)
    await _ensure_global_tenant(slug=tenant.slug, tenant_id=str(tenant.id))
    canceled = await async_client.post(f"/api/v1/jobs/{job_id}/cancel", headers=headers)
    assert canceled.status_code == 200, canceled.text
    assert canceled.json()["job"]["status"] == DocumentJobStatus.CANCELED.value

    retried = await async_client.post(
        f"/api/v1/jobs/{job_id}/retry",
        json={"retry_failed_only": False},
        headers=headers,
    )
    assert retried.status_code == 200
    assert retried.json()["job"]["id"] == job_id


@pytest.mark.anyio
async def test_jobs_logs_endpoint(
    async_client, make_auth_headers, sessionmaker, data_factory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        job = DocumentJob(
            tenant_id=str(tenant.id),
            kind="pipeline",
            status=DocumentJobStatus.RUNNING.value,
            pipeline_profile_id=None,
            preset_id=None,
            input_sha256="a" * 64,
            request_hash="b" * 64,
            idempotency_key="idem-job-logs",
            template_code="TMP",
            template_version=1,
            correlation_id="corr-logs",
            created_by="user-1",
        )
        session.add(job)
        await session.flush()
        step = DocumentJobStep(
            tenant_id=str(tenant.id),
            job_id=job.id,
            step_code="render_docx",
            step_key="render_docx",
            status=JobStepStatus.RUNNING.value,
            logs_uri=f"s3://{tenant.id}/jobs/{job.id}/render_docx.jsonl",
        )
        session.add(step)
        await session.commit()
        job_id = job.id
        step_id = step.id

    from app.services.file_storage import FileStorageService

    storage = FileStorageService.default()
    storage.put(
        f"{tenant.id}/jobs/{job_id}/render_docx.jsonl",
        b'{"timestamp":"2026-01-01T00:00:00Z","level":"info","message":"ok","meta":{}}\n',
        content_type="application/jsonl",
    )

    headers = await make_auth_headers()
    headers["x-tenant"] = str(tenant.id)
    await _ensure_global_tenant(slug=tenant.slug, tenant_id=str(tenant.id))
    resp = await async_client.get(f"/api/v1/jobs/{job_id}/steps/{step_id}/logs", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["lines"]


@pytest.mark.anyio
async def test_create_job_endpoint_without_idempotency_key(
    async_client, make_auth_headers, sessionmaker, data_factory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
    await _ensure_global_tenant(slug=tenant.slug, tenant_id=str(tenant.id))
    headers = await make_auth_headers()
    headers["x-tenant"] = str(tenant.id)

    profile_payload = {
        "code": "jobs_default_v2",
        "name": "Jobs default v2",
        "steps": [{"code": "render_docx", "required": True, "params_schema": "RenderParamsV1"}],
        "limits": {"max_parallel": 2, "max_parallel_per_step": {}},
        "is_active": True,
    }
    created = await async_client.post(
        "/api/v1/pipelines/profiles", json=profile_payload, headers=headers
    )
    assert created.status_code == 201, created.text
    profile_id = created.json()["id"]

    payload = {"profile_id": profile_id, "inputs": {"x": 1}, "options": {"run_async": True}}
    resp = await async_client.post("/api/v1/jobs", json=payload, headers=headers)
    assert resp.status_code == 202
    body = resp.json()
    assert body["correlation_id"]
    assert body["steps"]


@pytest.mark.anyio
async def test_jobs_logs_endpoint_reads_logs_file_id(
    async_client, make_auth_headers, sessionmaker, data_factory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        job = DocumentJob(
            tenant_id=str(tenant.id),
            kind="pipeline",
            status=DocumentJobStatus.RUNNING.value,
            pipeline_profile_id=None,
            preset_id=None,
            input_sha256="a" * 64,
            request_hash="b" * 64,
            idempotency_key="idem-job-logs-file-id",
            template_code="TMP",
            template_version=1,
            correlation_id="corr-logs-file-id",
            created_by="user-1",
        )
        session.add(job)
        await session.flush()

        file_record = FileRecord(
            tenant_id=str(tenant.id),
            bucket="main",
            object_key=f"logs/jobs/{job.id}/render_docx.jsonl",
            content_type="application/jsonl",
            size_bytes=0,
            sha256="f" * 64,
            status=FileStatus.clean.value,
            av_result_json={},
            metadata_json={"display_name": "render_docx.jsonl"},
        )
        session.add(file_record)
        await session.flush()

        step = DocumentJobStep(
            tenant_id=str(tenant.id),
            job_id=job.id,
            step_code="render_docx",
            step_key="render_docx",
            status=JobStepStatus.RUNNING.value,
            logs_uri=None,
            logs_file_id=file_record.id,
        )
        session.add(step)
        await session.commit()
        job_id = job.id
        step_id = step.id
        log_key = file_record.object_key

    from app.services.file_storage import FileStorageService

    storage = FileStorageService.default()
    storage.put(
        log_key,
        b'{"timestamp":"2026-01-01T00:00:00Z","level":"info","message":"ok-file-id","meta":{}}\n',
        content_type="application/jsonl",
    )

    headers = await make_auth_headers()
    headers["x-tenant"] = str(tenant.id)
    await _ensure_global_tenant(slug=tenant.slug, tenant_id=str(tenant.id))
    resp = await async_client.get(f"/api/v1/jobs/{job_id}/steps/{step_id}/logs", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["logs_uri"] == f"s3://{log_key}"
    assert body["lines"]


@pytest.mark.anyio
@pytest.mark.skipif(
    __import__("sys").platform == "win32",
    reason="WebSocket test not reliable on Windows (OS-level PermissionError in jsdom)",
)
async def test_jobs_ws_stream_endpoint(
    async_client, make_auth_headers, sessionmaker, data_factory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        job = DocumentJob(
            tenant_id=str(tenant.id),
            kind="pipeline",
            status=DocumentJobStatus.QUEUED.value,
            pipeline_profile_id=None,
            preset_id=None,
            input_sha256="a" * 64,
            request_hash="b" * 64,
            idempotency_key="idem-job-stream",
            template_code="TMP",
            template_version=1,
            correlation_id="corr-stream",
            created_by="user-1",
        )
        session.add(job)
        await session.flush()
        session.add(
            DocumentJobStep(
                tenant_id=str(tenant.id),
                job_id=job.id,
                step_code="render_docx",
                step_key="render_docx",
                status=JobStepStatus.QUEUED.value,
                attempts=0,
            )
        )
        await session.commit()

    headers = await make_auth_headers()
    headers["x-tenant"] = str(tenant.id)
    await _ensure_global_tenant(slug=tenant.slug, tenant_id=str(tenant.id))

    response = await async_client.get(f"/api/v1/jobs/ws/jobs/{job.id}", headers=headers)
    assert response.status_code == 200
    assert "text/event-stream" in response.headers.get("content-type", "")
    assert "step_status_changed" in response.text


@pytest.mark.anyio
async def test_job_steps_timeline_endpoint(
    async_client, make_auth_headers, sessionmaker, data_factory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        job = DocumentJob(
            tenant_id=str(tenant.id),
            kind="pipeline",
            status=DocumentJobStatus.RUNNING.value,
            pipeline_profile_id=None,
            preset_id=None,
            input_sha256="a" * 64,
            request_hash="b" * 64,
            idempotency_key="idem-job-timeline",
            template_code="TMP",
            template_version=1,
            correlation_id="corr-timeline",
            created_by="user-1",
        )
        session.add(job)
        await session.flush()
        session.add_all(
            [
                DocumentJobStep(
                    tenant_id=str(tenant.id),
                    job_id=job.id,
                    step_code="render_docx",
                    status=JobStepStatus.SUCCESS.value,
                    attempt=1,
                    max_attempts=1,
                ),
                DocumentJobStep(
                    tenant_id=str(tenant.id),
                    job_id=job.id,
                    step_code="convert_pdf",
                    status=JobStepStatus.RUNNING.value,
                    attempt=1,
                    max_attempts=2,
                ),
            ]
        )
        await session.commit()
        job_id = job.id

    headers = await make_auth_headers()
    headers["x-tenant"] = str(tenant.id)
    await _ensure_global_tenant(slug=tenant.slug, tenant_id=str(tenant.id))
    resp = await async_client.get(f"/api/v1/jobs/{job_id}/steps", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert {step["code"] for step in body} == {"render_docx", "convert_pdf"}


@pytest.mark.anyio
async def test_retry_job_with_step_code_query(
    async_client, make_auth_headers, sessionmaker, data_factory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        job = DocumentJob(
            tenant_id=str(tenant.id),
            kind="pipeline",
            status=DocumentJobStatus.FAILED.value,
            pipeline_profile_id=None,
            preset_id=None,
            input_sha256="a" * 64,
            request_hash="b" * 64,
            idempotency_key="idem-job-retry-query",
            template_code="TMP",
            template_version=1,
            correlation_id="corr-retry-query",
            created_by="user-1",
        )
        session.add(job)
        await session.flush()
        session.add(
            DocumentJobStep(
                tenant_id=str(tenant.id),
                job_id=job.id,
                step_code="convert_pdf",
                status=JobStepStatus.FAILED.value,
                attempt=1,
                max_attempts=2,
                error_code="step_failed",
            )
        )
        await session.commit()
        job_id = job.id

    headers = await make_auth_headers()
    headers["x-tenant"] = str(tenant.id)
    await _ensure_global_tenant(slug=tenant.slug, tenant_id=str(tenant.id))
    resp = await async_client.post(
        f"/api/v1/jobs/{job_id}/retry", params={"step_code": "convert_pdf"}, headers=headers
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["job"]["id"] == job_id


@pytest.mark.anyio
async def test_get_job_returns_404_when_job_belongs_to_different_tenant(
    async_client,
    make_auth_headers,
    sessionmaker,
    data_factory,
) -> None:
    """Cross-tenant: id известен, но строка job привязана к другой аренде — не отдавать ресурс."""
    async with sessionmaker() as session:
        tenant_owner = await data_factory.ensure_tenant(slug="jobs-owner", session=session)
        tenant_other = await data_factory.ensure_tenant(slug="jobs-other", session=session)
        job = DocumentJob(
            tenant_id=str(tenant_owner.id),
            kind="pipeline",
            status=DocumentJobStatus.QUEUED.value,
            pipeline_profile_id=None,
            preset_id=None,
            input_sha256="c" * 64,
            request_hash="d" * 64,
            idempotency_key="idem-cross-tenant-job",
            template_code="TMP",
            template_version=1,
            correlation_id="corr-cross",
            created_by="user-1",
        )
        session.add(job)
        await session.commit()
        job_id = job.id

    await _ensure_global_tenant(slug=tenant_owner.slug, tenant_id=str(tenant_owner.id))
    await _ensure_global_tenant(slug=tenant_other.slug, tenant_id=str(tenant_other.id))

    headers = await make_auth_headers()
    headers["x-tenant"] = str(tenant_other.id)
    response = await async_client.get(f"/api/v1/jobs/{job_id}", headers=headers)
    assert response.status_code == 404
