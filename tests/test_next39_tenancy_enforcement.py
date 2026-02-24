from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.mark.anyio
async def test_business_route_requires_x_tenant(app_fixture) -> None:
    transport = ASGITransport(app=app_fixture, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/v1/templates")

    assert response.status_code == 400
    body = response.json()
    assert body["code"] == "TENANT_REQUIRED"
    assert body["message"] == "X-Tenant header required"


@pytest.mark.anyio
async def test_healthz_without_tenant_is_public(app_fixture) -> None:
    transport = ASGITransport(app=app_fixture, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/healthz")
    assert response.status_code == 200


@pytest.mark.anyio
async def test_invalid_tenant_uuid_returns_400(app_fixture) -> None:
    transport = ASGITransport(app=app_fixture, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/v1/templates", headers={"X-Tenant": "does-not-exist"})

    assert response.status_code == 400
    body = response.json()
    assert body["code"] == "TENANT_INVALID"


@pytest.mark.anyio
async def test_valid_tenant_uuid_allows_request(app_fixture) -> None:
    transport = ASGITransport(app=app_fixture, raise_app_exceptions=False)
    tenant_id = "00000000-0000-0000-0000-000000000000"
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/v1/templates", headers={"X-Tenant": tenant_id})

    assert response.status_code in {200, 401, 403, 404}
