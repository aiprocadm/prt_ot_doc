from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from starlette import status

from app.middleware.tenant import TenantMiddleware
from app.models.models import RoleEnum


@pytest.fixture(autouse=True)
def _bypass_tenant_middleware(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _dispatch_passthrough(self, request, call_next):  # type: ignore[no-untyped-def]
        return await call_next(request)

    monkeypatch.setattr(TenantMiddleware, "dispatch", _dispatch_passthrough)


@pytest.mark.anyio
async def test_missing_tenant_header_returns_structured_error(app_fixture) -> None:
    transport = ASGITransport(app=app_fixture, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/v1/tenants")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    body = response.json()
    assert body["code"] == "TENANT_REQUIRED"
    assert body["error_code"] == "TENANT_REQUIRED"
    assert body["message"] == "X-Tenant header required"
    assert body["trace_id"]
    assert body["request_id"] == body["trace_id"]


@pytest.mark.anyio
async def test_forbidden_access_returns_structured_error(
    async_client: AsyncClient, make_auth_headers
) -> None:
    headers = {**dict(async_client.headers), **await make_auth_headers(RoleEnum.CLIENT_USER)}
    response = await async_client.get("/api/v1/tenants", headers=headers)

    assert response.status_code == status.HTTP_403_FORBIDDEN
    body = response.json()
    assert body["code"] == "FORBIDDEN"
    assert body["error_code"] == "FORBIDDEN"
    assert body["message"] == "Forbidden"
    assert body["trace_id"]
    assert body["request_id"] == body["trace_id"]
