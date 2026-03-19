from __future__ import annotations

import pytest
from app.modules.pipelines.models import PipelineProfile
from httpx import ASGITransport, AsyncClient


@pytest.mark.anyio
async def test_business_route_requires_tenant_header(app_fixture, make_auth_headers) -> None:
    headers = await make_auth_headers()
    headers.pop("x-tenant", None)
    transport = ASGITransport(app=app_fixture)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/v1/templates", headers=headers)

    assert response.status_code == 400
    assert response.json()["code"] == "TENANT_REQUIRED"


@pytest.mark.anyio
async def test_pipeline_idempotency_same_key_same_result(
    app_fixture, make_auth_headers, sessionmaker, data_factory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        session.add(
            PipelineProfile(
                tenant_id=str(tenant.id),
                code="final_regression",
                name="Final Regression",
                steps=[{"code": "render_docx"}],
                limits={"max_parallel": 1},
                is_active=True,
            )
        )
        await session.commit()

    headers = await make_auth_headers()
    headers["Idempotency-Key"] = "final-regression-idem"
    payload = {"profile_code": "final_regression", "inputs": {"doc": "ok"}, "options": {}}

    transport = ASGITransport(app=app_fixture)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        first = await client.post("/api/v1/pipelines/run", json=payload, headers=headers)
        second = await client.post("/api/v1/pipelines/run", json=payload, headers=headers)

    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["run_id"] == second.json()["run_id"]


@pytest.mark.anyio
async def test_template_selection_by_code_version_not_found_returns_conflict(
    async_client, make_auth_headers
) -> None:
    headers = await make_auth_headers()
    response = await async_client.get(
        "/api/v1/templates/by-code/unknown-template",
        params={"version": 999},
        headers=headers,
    )

    assert response.status_code == 409
    assert response.json()["code"] == "template_version_not_found"


@pytest.mark.anyio
async def test_tenant_guard_error_payload_includes_release_contract_fields(
    app_fixture, make_auth_headers
) -> None:
    headers = await make_auth_headers()
    headers.pop("x-tenant", None)
    transport = ASGITransport(app=app_fixture)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/v1/templates", headers=headers)

    assert response.status_code == 400
    body = response.json()
    assert body["code"] == "TENANT_REQUIRED"
    assert body["type"] == "tenancy"
    assert body["correlation_id"] == body["trace_id"]
    assert body["timestamp"]
    assert "field_errors" in body
