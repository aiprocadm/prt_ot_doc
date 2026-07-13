"""RBAC guards for the staff-side client-portal package routers (sweep row 4).

api/routes/client_portal.py mounts THREE routers. `/portal/*` is correctly
protected by its own portal-token dependency (`_portal_auth`). But the sibling
`internal_router` (`/api/v1/packages/*`) and `presets_router`
(`/api/v1/presets/packages/*`) carried only get_session + get_tenant_record —
reachable by any role without a valid token. The worst was
`POST /packages/runs/{run_id}/portal-link`, which mints a ClientPortalToken.

read = MGMT_READ, write = DOC_WRITE (mirror 618614d9).
"""

from __future__ import annotations

import pytest

from app.models.models import RoleEnum

_FAKE_ID = "00000000-0000-0000-0000-000000000000"


@pytest.mark.anyio
async def test_presets_list_forbidden_for_worker(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.WORKER)
    response = await async_client.get("/api/v1/presets/packages", headers=headers)
    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


@pytest.mark.anyio
async def test_presets_list_allowed_for_line_manager(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.LINE_MANAGER)
    response = await async_client.get("/api/v1/presets/packages", headers=headers)
    assert response.status_code != 403


@pytest.mark.anyio
async def test_presets_create_forbidden_for_line_manager(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.LINE_MANAGER)
    response = await async_client.post("/api/v1/presets/packages", json={}, headers=headers)
    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


@pytest.mark.anyio
async def test_presets_create_allowed_for_ot_specialist(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.OT_SPECIALIST)
    response = await async_client.post("/api/v1/presets/packages", json={}, headers=headers)
    assert response.status_code != 403


@pytest.mark.anyio
async def test_packages_runs_list_forbidden_for_worker(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.WORKER)
    response = await async_client.get("/api/v1/packages/runs", headers=headers)
    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


@pytest.mark.anyio
async def test_portal_link_mint_forbidden_for_line_manager(async_client, make_auth_headers) -> None:
    """The credential-minting endpoint must reject a read-only role."""
    headers = await make_auth_headers(RoleEnum.LINE_MANAGER)
    response = await async_client.post(
        f"/api/v1/packages/runs/{_FAKE_ID}/portal-link", json={}, headers=headers
    )
    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


@pytest.mark.anyio
async def test_portal_link_mint_allowed_for_ot_specialist(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.OT_SPECIALIST)
    response = await async_client.post(
        f"/api/v1/packages/runs/{_FAKE_ID}/portal-link", json={}, headers=headers
    )
    assert response.status_code != 403
