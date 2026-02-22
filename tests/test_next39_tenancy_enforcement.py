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
async def test_invalid_tenant_returns_not_found(app_fixture) -> None:
    transport = ASGITransport(app=app_fixture, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/v1/templates", headers={"X-Tenant": "does-not-exist"})

    assert response.status_code == 404
    body = response.json()
    assert body["code"] == "TENANT_NOT_FOUND"
