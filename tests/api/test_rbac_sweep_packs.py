"""RBAC guards for the packs-v2 router (``app.modules.packs.api``).

The router is mounted with NO prefix under ``/api/v1`` (see
``app.api.v1.route_groups`` -> ``(packs_v2_api.router, {})``), so its routes
live at ``/api/v1/package-profiles``, ``/api/v1/package-presets`` and
``/api/v1/pack-runs`` — NOT under ``/api/v1/packs``.

Every listed endpoint was previously protected only by tenant-scoping
(``get_session`` + ``get_tenant_record``), so any authenticated tenant user —
including a rank-and-file worker — could reach them. All reads now require
``_PACKS_READ_ROLES`` and all writes/mutations ``_PACKS_WRITE_ROLES``; the two
shared deps mean a few representative tests cover the whole surface.
"""

from __future__ import annotations

import pytest

from app.models.models import RoleEnum


@pytest.mark.anyio
async def test_packs_read_forbidden_for_worker(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.WORKER)

    response = await async_client.get("/api/v1/package-profiles", headers=headers)

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


@pytest.mark.anyio
async def test_packs_read_allowed_for_ot_specialist(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.OT_SPECIALIST)

    response = await async_client.get("/api/v1/package-profiles", headers=headers)

    assert response.status_code == 200


@pytest.mark.anyio
async def test_pack_runs_read_forbidden_for_worker(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.WORKER)

    response = await async_client.get("/api/v1/pack-runs", headers=headers)

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


@pytest.mark.anyio
async def test_packs_write_forbidden_for_worker(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.WORKER)

    response = await async_client.post(
        "/api/v1/package-profiles",
        json={"code": "prof-1", "name": "Profile 1"},
        headers=headers,
    )

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


@pytest.mark.anyio
async def test_packs_write_forbidden_for_line_manager(async_client, make_auth_headers) -> None:
    """line_manager may read packs but not create profiles (read/write split)."""
    headers = await make_auth_headers(RoleEnum.LINE_MANAGER)

    response = await async_client.post(
        "/api/v1/package-profiles",
        json={"code": "prof-2", "name": "Profile 2"},
        headers=headers,
    )

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


@pytest.mark.anyio
async def test_packs_write_allowed_for_ot_specialist(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.OT_SPECIALIST)

    response = await async_client.post(
        "/api/v1/package-profiles",
        json={"code": "prof-ok", "name": "Profile OK"},
        headers=headers,
    )

    assert response.status_code == 201
