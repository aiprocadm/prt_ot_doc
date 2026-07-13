"""RBAC guards for tenants reads / ws_stub / files-reindex / search-reindex
(sweep rows 9-12).

* tenants.py: GET /tenants, /admin/tenants used an optional-bearer bypass
  (`if credentials:`), and GET /tenants/me had no auth wiring at all -> unauth
  tenant metadata/quota disclosure. Lists -> abac(TENANT_ADMIN); /me -> authn-only.
* ws_stub.py GET /ws/v1/events leaked Outbox event/destination metadata -> abac(ADMIN_OWNER).
* modules/files/api.py POST /{file_id}:reindex missed its sibling guard -> module WRITE dep.
* modules/search/api.py POST /search/reindex[/{entity}] triggered full rebuilds -> abac(ADMIN_OWNER).
"""

from __future__ import annotations

import pytest

from app.models.models import RoleEnum

_FAKE_ID = "00000000-0000-0000-0000-000000000000"


# ---------------------------------------------------------------- tenants


@pytest.mark.anyio
async def test_tenants_list_requires_authentication(async_client, make_auth_headers) -> None:
    """The optional-bearer bypass: no token (tenant slug only) must not return data."""
    headers = await make_auth_headers(RoleEnum.WORKER)
    headers.pop("Authorization", None)
    response = await async_client.get("/api/v1/tenants", headers=headers)
    assert response.status_code in (401, 403)


@pytest.mark.anyio
async def test_tenants_list_forbidden_for_worker(async_client, make_auth_headers) -> None:
    """An authenticated non-admin role is also rejected (already held via _require_admin)."""
    headers = await make_auth_headers(RoleEnum.WORKER)
    response = await async_client.get("/api/v1/tenants", headers=headers)
    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


@pytest.mark.anyio
async def test_tenants_admin_list_requires_authentication(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.WORKER)
    headers.pop("Authorization", None)
    response = await async_client.get("/api/v1/admin/tenants", headers=headers)
    assert response.status_code in (401, 403)


@pytest.mark.anyio
async def test_tenants_list_allowed_for_admin(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)
    response = await async_client.get("/api/v1/tenants", headers=headers)
    assert response.status_code != 403


@pytest.mark.anyio
async def test_tenants_me_requires_authentication(async_client, make_auth_headers) -> None:
    """GET /tenants/me must reject an unauthenticated caller (tenant slug only)."""
    headers = await make_auth_headers(RoleEnum.WORKER)
    headers.pop("Authorization", None)
    response = await async_client.get("/api/v1/tenants/me", headers=headers)
    assert response.status_code in (401, 403)


@pytest.mark.anyio
async def test_tenants_me_allowed_for_authenticated_member(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.WORKER)
    response = await async_client.get("/api/v1/tenants/me", headers=headers)
    assert response.status_code != 403


# ---------------------------------------------------------------- ws_stub


@pytest.mark.anyio
async def test_ws_events_forbidden_for_worker(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.WORKER)
    response = await async_client.get("/ws/v1/events", headers=headers)
    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


@pytest.mark.anyio
async def test_ws_events_allowed_for_admin(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)
    response = await async_client.get("/ws/v1/events", headers=headers)
    assert response.status_code != 403


# ---------------------------------------------------------------- files reindex


@pytest.mark.anyio
async def test_files_reindex_forbidden_for_worker(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.WORKER)
    response = await async_client.post(f"/api/v1/files/{_FAKE_ID}:reindex", headers=headers)
    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


@pytest.mark.anyio
async def test_files_reindex_allowed_for_admin(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)
    response = await async_client.post(f"/api/v1/files/{_FAKE_ID}:reindex", headers=headers)
    assert response.status_code != 403


# ---------------------------------------------------------------- search reindex


@pytest.mark.anyio
async def test_search_reindex_forbidden_for_worker(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.WORKER)
    response = await async_client.post("/api/v1/search/reindex", headers=headers)
    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


@pytest.mark.anyio
async def test_search_reindex_allowed_for_admin(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)
    response = await async_client.post("/api/v1/search/reindex", headers=headers)
    assert response.status_code != 403
