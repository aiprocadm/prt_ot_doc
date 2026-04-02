from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.models.job_engine import DocumentJob, DocumentJobStatus, DocumentJobStep, JobStepStatus


@pytest.mark.anyio
async def test_cancel_and_retry_failed_only(app_fixture, make_auth_headers, sessionmaker, data_factory) -> None:
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
            idempotency_key="idem-job-flow",
            template_code="TMP",
            template_version=1,
            correlation_id="corr-flow",
            created_by="user-1",
        )
        session.add(job)
        await session.flush()
        session.add_all([
            DocumentJobStep(tenant_id=str(tenant.id), job_id=job.id, step_code="render_docx", order=1, status=JobStepStatus.SUCCESS.value, attempts=1),
            DocumentJobStep(tenant_id=str(tenant.id), job_id=job.id, step_code="convert_pdf", order=2, status=JobStepStatus.FAILED.value, attempts=1),
        ])
        await session.commit()
        job_id = job.id

    headers = await make_auth_headers()
    transport = ASGITransport(app=app_fixture)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        canceled = await client.post(f"/api/v1/jobs/{job_id}:cancel", headers=headers)
        assert canceled.status_code == 200
        assert canceled.json()["job"]["status"] == "canceled"

        retried = await client.post(f"/api/v1/jobs/{job_id}:retry", json={"retry_failed_only": True}, headers=headers)
        assert retried.status_code == 200
        step_status = {s["code"]: s["status"] for s in retried.json()["steps"]}
        assert step_status["render_docx"] == "success"
