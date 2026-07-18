"""RBAC guards for public_api key-management + marketplace (sweep rows 1-2).

The most severe finding of the sweep. `admin_router` (`/api/v1/machine-keys`) had
no auth: `POST /machine-keys` minted a tenant API key with caller-supplied scopes
(incl. api:admin) and returned the plaintext token — a full auth-bootstrap bypass /
privilege escalation. `marketplace_router` (`/api/v1/marketplace`) was likewise open.

Both routers are guarded at router level with abac(ADMIN_OWNER = admin/owner).
"""

from __future__ import annotations

import pytest

from app.models.models import RoleEnum

_FAKE_ID = "00000000-0000-0000-0000-000000000000"


# ---------------------------------------------------------------- machine-keys


@pytest.mark.anyio
async def test_machine_keys_list_forbidden_for_worker(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.WORKER)
    response = await async_client.get("/api/v1/machine-keys", headers=headers)
    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


@pytest.mark.anyio
async def test_machine_keys_issue_forbidden_for_ot_specialist(
    async_client, make_auth_headers
) -> None:
    """Issuing an API key is admin/owner only — an OT specialist must be rejected."""
    headers = await make_auth_headers(RoleEnum.OT_SPECIALIST)
    response = await async_client.post(
        "/api/v1/machine-keys", json={"name": "t", "scopes": ["api:read"]}, headers=headers
    )
    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


@pytest.mark.anyio
async def test_machine_keys_list_allowed_for_admin(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)
    response = await async_client.get("/api/v1/machine-keys", headers=headers)
    assert response.status_code == 200


@pytest.mark.anyio
async def test_machine_keys_issue_allowed_for_admin(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)
    response = await async_client.post(
        "/api/v1/machine-keys", json={"name": "t", "scopes": ["api:read"]}, headers=headers
    )
    assert response.status_code != 403


# ---------------------------------------------------------------- marketplace


@pytest.mark.anyio
async def test_marketplace_list_forbidden_for_worker(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.WORKER)
    response = await async_client.get("/api/v1/marketplace", headers=headers)
    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


@pytest.mark.anyio
async def test_marketplace_publish_forbidden_for_worker(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.WORKER)
    response = await async_client.post("/api/v1/marketplace", json={}, headers=headers)
    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


@pytest.mark.anyio
async def test_marketplace_list_allowed_for_admin(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)
    response = await async_client.get("/api/v1/marketplace", headers=headers)
    assert response.status_code != 403
