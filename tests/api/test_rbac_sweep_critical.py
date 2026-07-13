"""RBAC/auth guards for Tier-1 (auth-bypass) and Tier-2 (credential/priv-esc) routers.

Follow-up to the /analytics + /exports fix (commit 618614d9): the systematic
route-group audit (docs/audit/RBAC_ROUTE_GROUP_AUDIT_2026-07-12.md) found the
same class of hole across 18 modules. This file locks the contract for the
security-critical tiers:

* TIER 1 — MISSING AUTHENTICATION: ``POST /search/reindex[/{entity_type}]`` and
  the ``/tenants`` listings were reachable with only a tenant-slug header and
  NO bearer token (``get_session`` + ``get_tenant_record`` never inspect the
  token; ``tenants`` used ``HTTPBearer(auto_error=False)`` + role check inside
  ``if credentials:``). Contract: unauthenticated → 401/403, worker → 403,
  admin → 200.
* TIER 2 — CREDENTIAL MINTING / PRIVILEGE ESCALATION: ``/machine-keys`` (mint /
  rotate / revoke / list — returns plaintext secrets) and ``/marketplace``
  publish/install on public_api, plus the client-portal ``portal-link`` minting
  endpoint, were role-less. Contract: worker → 403, admin → 200/201.
"""

from __future__ import annotations

import pytest

from app.models.models import RoleEnum


def _no_token(headers: dict[str, str]) -> dict[str, str]:
    """Keep the tenant-slug context but drop the bearer token."""
    stripped = dict(headers)
    stripped.pop("Authorization", None)
    return stripped


# --------------------------------------------------------------------------- #
# TIER 1 — search reindex (was unauthenticated + role-less)
# --------------------------------------------------------------------------- #
@pytest.mark.anyio
async def test_search_reindex_requires_authentication(async_client, make_auth_headers) -> None:
    headers = _no_token(await make_auth_headers(RoleEnum.ADMIN))

    response = await async_client.post("/api/v1/search/reindex", headers=headers)

    assert response.status_code in (401, 403)


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

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.anyio
async def test_search_reindex_by_entity_forbidden_for_worker(
    async_client, make_auth_headers
) -> None:
    headers = await make_auth_headers(RoleEnum.WORKER)

    response = await async_client.post("/api/v1/search/reindex/person", headers=headers)

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


@pytest.mark.anyio
async def test_search_reindex_by_entity_allowed_for_admin(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)

    response = await async_client.post("/api/v1/search/reindex/person", headers=headers)

    assert response.status_code == 200


# --------------------------------------------------------------------------- #
# TIER 1 — tenants listings (auth bypass via HTTPBearer(auto_error=False))
# --------------------------------------------------------------------------- #
@pytest.mark.anyio
async def test_tenants_list_requires_authentication(async_client, make_auth_headers) -> None:
    headers = _no_token(await make_auth_headers(RoleEnum.ADMIN))

    response = await async_client.get("/api/v1/tenants", headers=headers)

    assert response.status_code in (401, 403)


@pytest.mark.anyio
async def test_tenants_list_forbidden_for_worker(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.WORKER)

    response = await async_client.get("/api/v1/tenants", headers=headers)

    assert response.status_code == 403


@pytest.mark.anyio
async def test_tenants_list_allowed_for_admin(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)

    response = await async_client.get("/api/v1/tenants", headers=headers)

    assert response.status_code == 200


@pytest.mark.anyio
async def test_admin_tenants_list_requires_authentication(async_client, make_auth_headers) -> None:
    headers = _no_token(await make_auth_headers(RoleEnum.ADMIN))

    response = await async_client.get("/api/v1/admin/tenants", headers=headers)

    assert response.status_code in (401, 403)


@pytest.mark.anyio
async def test_tenants_me_forbidden_for_worker(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.WORKER)

    response = await async_client.get("/api/v1/tenants/me", headers=headers)

    assert response.status_code == 403


@pytest.mark.anyio
async def test_tenants_me_allowed_for_admin(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)

    response = await async_client.get("/api/v1/tenants/me", headers=headers)

    assert response.status_code == 200


# --------------------------------------------------------------------------- #
# TIER 2 — public_api machine-keys (mint / rotate / revoke → plaintext secrets)
# --------------------------------------------------------------------------- #
@pytest.mark.anyio
async def test_machine_keys_list_forbidden_for_worker(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.WORKER)

    response = await async_client.get("/api/v1/machine-keys", headers=headers)

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


@pytest.mark.anyio
async def test_machine_keys_list_allowed_for_admin(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)

    response = await async_client.get("/api/v1/machine-keys", headers=headers)

    assert response.status_code == 200


@pytest.mark.anyio
async def test_machine_keys_issue_forbidden_for_worker(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.WORKER)

    response = await async_client.post(
        "/api/v1/machine-keys",
        json={"name": "ci-key", "scopes": ["api:read"]},
        headers=headers,
    )

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


@pytest.mark.anyio
async def test_machine_keys_issue_allowed_for_admin(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)

    response = await async_client.post(
        "/api/v1/machine-keys",
        json={"name": "ci-key", "scopes": ["api:read"]},
        headers=headers,
    )

    assert response.status_code == 201
    assert response.json()["token"]


# --------------------------------------------------------------------------- #
# TIER 2 — public_api marketplace (publish / install tenant content)
# --------------------------------------------------------------------------- #
_MARKETPLACE_ITEM = {
    "item_type": "package_preset",
    "code": "mp-code",
    "name": "MP Item",
    "version_label": "1.0",
}


@pytest.mark.anyio
async def test_marketplace_publish_forbidden_for_worker(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.WORKER)

    response = await async_client.post(
        "/api/v1/marketplace", json=_MARKETPLACE_ITEM, headers=headers
    )

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


@pytest.mark.anyio
async def test_marketplace_publish_allowed_for_admin(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)

    response = await async_client.post(
        "/api/v1/marketplace", json=_MARKETPLACE_ITEM, headers=headers
    )

    assert response.status_code == 201


@pytest.mark.anyio
async def test_marketplace_install_forbidden_for_worker(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.WORKER)

    response = await async_client.post(
        "/api/v1/marketplace/some-item-id/install", json={}, headers=headers
    )

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


# --------------------------------------------------------------------------- #
# TIER 2/3 — client_portal internal package presets / runs / portal-link
# --------------------------------------------------------------------------- #
@pytest.mark.anyio
async def test_portal_presets_list_forbidden_for_worker(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.WORKER)

    response = await async_client.get("/api/v1/presets/packages", headers=headers)

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


@pytest.mark.anyio
async def test_portal_presets_list_allowed_for_ot_specialist(
    async_client, make_auth_headers
) -> None:
    headers = await make_auth_headers(RoleEnum.OT_SPECIALIST)

    response = await async_client.get("/api/v1/presets/packages", headers=headers)

    assert response.status_code == 200


@pytest.mark.anyio
async def test_portal_preset_create_forbidden_for_line_manager(
    async_client, make_auth_headers
) -> None:
    """line_manager may read presets but not create them (read/write split)."""
    headers = await make_auth_headers(RoleEnum.LINE_MANAGER)

    response = await async_client.post(
        "/api/v1/presets/packages", json={"code": "p1", "name": "Preset 1"}, headers=headers
    )

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


@pytest.mark.anyio
async def test_portal_preset_create_allowed_for_ot_specialist(
    async_client, make_auth_headers
) -> None:
    headers = await make_auth_headers(RoleEnum.OT_SPECIALIST)

    response = await async_client.post(
        "/api/v1/presets/packages", json={"code": "p1", "name": "Preset 1"}, headers=headers
    )

    assert response.status_code == 201


@pytest.mark.anyio
async def test_portal_run_create_forbidden_for_worker(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.WORKER)

    response = await async_client.post(
        "/api/v1/packages/runs", json={"preset_code": "whatever"}, headers=headers
    )

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


@pytest.mark.anyio
async def test_portal_link_forbidden_for_ot_specialist(async_client, make_auth_headers) -> None:
    """Minting an external magic-link is tighter than general write access."""
    headers = await make_auth_headers(RoleEnum.OT_SPECIALIST)

    response = await async_client.post(
        "/api/v1/packages/runs/some-run/portal-link", headers=headers
    )

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


@pytest.mark.anyio
async def test_portal_link_passes_guard_for_admin(async_client, make_auth_headers) -> None:
    """Admin clears the role guard; a missing run then yields 404 (not 403)."""
    headers = await make_auth_headers(RoleEnum.ADMIN)

    response = await async_client.post(
        "/api/v1/packages/runs/nonexistent-run/portal-link", headers=headers
    )

    assert response.status_code == 404
