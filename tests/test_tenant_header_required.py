from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.mark.anyio
async def test_missing_tenant_header_returns_400(app_fixture, make_auth_headers) -> None:
    transport = ASGITransport(app=app_fixture)
    headers = await make_auth_headers()
    headers.pop("x-tenant", None)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/v1/tenants", headers=headers)

    assert response.status_code == 400
    payload = response.json()
    assert payload["code"] == "tenant_header_missing"
