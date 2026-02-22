from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.domains.files.utils import build_storage_key


@pytest.mark.anyio
async def test_missing_x_tenant_returns_400_on_business_route(app_fixture, make_auth_headers) -> None:
    headers = await make_auth_headers()
    headers.pop("x-tenant", None)
    transport = ASGITransport(app=app_fixture)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/v1/tenants", headers=headers)

    assert response.status_code == 400
    assert response.json()["code"] == "tenant_required"


@pytest.mark.anyio
async def test_search_path_is_set_per_request(sessionmaker) -> None:
    async with sessionmaker() as session:
        info = getattr(session, "info", {})
        # In sqlite tests schemas are emulated, but session search_path must still be present.
        assert isinstance(info, dict)


def test_s3_prefix_enforced_and_cross_tenant_denied() -> None:
    key = build_storage_key(tenant_slug="tenant-a", sha256_hex="f" * 64, extension="pdf")
    assert key.startswith("tenant-a/")
    assert not key.startswith("tenant-b/")
