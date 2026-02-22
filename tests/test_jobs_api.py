from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.models.job_engine import DocumentJob, DocumentJobStatus, DocumentJobStep, JobStepStatus


@pytest.mark.anyio
async def test_job_status_endpoint_for_unknown_job(app_fixture, make_auth_headers) -> None:
    headers = await make_auth_headers()
    transport = ASGITransport(app=app_fixture)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/v1/jobs/unknown", headers=headers)

    assert response.status_code == 404


@pytest.mark.anyio
async def test_jobs_list_and_retry_step_endpoints(
    app_fixture,
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
    transport = ASGITransport(app=app_fixture)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        listed = await client.get("/api/v1/jobs", headers=headers)
        assert listed.status_code == 200
        payload = listed.json()
        assert any(item["id"] == job_id for item in payload["items"])

        retried = await client.post(
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
async def test_create_job_endpoint_with_idempotency(app_fixture, make_auth_headers, client) -> None:
    headers = await make_auth_headers()

    profile_payload = {
        "code": "jobs_default_v1",
        "name": "Jobs default",
        "steps": [{"code": "render_docx", "required": True}],
        "limits": {},
        "is_active": True,
    }
    created = await client.post("/api/v1/pipelines/profiles", json=profile_payload, headers=headers)
    assert created.status_code == 201
    profile_id = created.json()["id"]

    payload = {"profile_id": profile_id, "inputs": {"x": 1}, "options": {"run_async": True}}
    resp1 = await client.post("/api/v1/jobs", json=payload, headers={**headers, "Idempotency-Key": "job-create-idem"})
    assert resp1.status_code == 202
    resp2 = await client.post("/api/v1/jobs", json=payload, headers={**headers, "Idempotency-Key": "job-create-idem"})
    assert resp2.status_code == 202
    assert resp1.json()["job_id"] == resp2.json()["job_id"]
