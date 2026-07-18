from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.modules.pipelines.models import PipelineProfile


@pytest.mark.anyio
async def test_pipeline_run_idempotency_returns_same_job(
    app_fixture, make_auth_headers, sessionmaker, data_factory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        profile = PipelineProfile(
            tenant_id=str(tenant.id),
            code="doc_gen_default",
            name="Doc Gen",
            steps=[
                {"code": "render_docx"},
                {"code": "apply_headers"},
                {"code": "replace"},
                {"code": "convert_pdf"},
            ],
            limits={"max_parallel": 2},
            is_active=True,
        )
        session.add(profile)
        await session.commit()

    headers = await make_auth_headers()
    headers["Idempotency-Key"] = "next26-pipeline-idem"
    transport = ASGITransport(app=app_fixture)

    payload = {"profile_code": "doc_gen_default", "inputs": {"x": 1}, "options": {}}
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        first = await client.post("/api/v1/pipelines/run", json=payload, headers=headers)
        second = await client.post("/api/v1/pipelines/run", json=payload, headers=headers)

    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["run_id"] == second.json()["run_id"]
