"""RBAC guards for the /pipelines router (profiles CRUD + runs).

Part of the systematic RBAC route-group sweep
(docs/audit/RBAC_ROUTE_GROUP_AUDIT_2026-07-12.md). Before this fix every
endpoint under ``/api/v1/pipelines`` was protected only by tenant-scoping
(``get_session`` + ``get_tenant_record``), so any authenticated tenant user —
including a rank-and-file ``worker`` — could list/create profiles and start,
cancel or retry pipeline runs.

Contract:
* READ  (GET profiles/runs/events): worker → 403, ot_specialist → 200.
* WRITE (POST/PUT/PATCH/DELETE + :activate/:cancel/:retry): worker → 403,
  line_manager → 403 (read-only role), ot_specialist → 201.

All endpoints share the same two deps (PipelinesReadAccess /
PipelinesWriteAccess), so a representative sample locks the whole router.
"""

from __future__ import annotations

import pytest

from app.models.models import RoleEnum

_VALID_PROFILE = {
    "code": "sweep-pipe",
    "name": "Sweep Pipeline",
    "steps": [
        {"code": "render_docx", "required": True, "params_schema": "RenderParamsV1"},
    ],
}


# --------------------------------------------------------------------------- #
# READ — GET /pipelines/profiles
# --------------------------------------------------------------------------- #
@pytest.mark.anyio
async def test_pipelines_read_forbidden_for_worker(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.WORKER)

    response = await async_client.get("/api/v1/pipelines/profiles", headers=headers)

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


@pytest.mark.anyio
async def test_pipelines_read_allowed_for_ot_specialist(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.OT_SPECIALIST)

    response = await async_client.get("/api/v1/pipelines/profiles", headers=headers)

    assert response.status_code == 200


# --------------------------------------------------------------------------- #
# WRITE — POST /pipelines/profiles
# --------------------------------------------------------------------------- #
@pytest.mark.anyio
async def test_pipelines_write_forbidden_for_worker(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.WORKER)

    response = await async_client.post(
        "/api/v1/pipelines/profiles", json=_VALID_PROFILE, headers=headers
    )

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


@pytest.mark.anyio
async def test_pipelines_write_forbidden_for_line_manager(async_client, make_auth_headers) -> None:
    """line_manager may read pipelines but not create/mutate them (read/write split)."""
    headers = await make_auth_headers(RoleEnum.LINE_MANAGER)

    response = await async_client.post(
        "/api/v1/pipelines/profiles", json=_VALID_PROFILE, headers=headers
    )

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


@pytest.mark.anyio
async def test_pipelines_write_allowed_for_ot_specialist(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.OT_SPECIALIST)

    response = await async_client.post(
        "/api/v1/pipelines/profiles", json=_VALID_PROFILE, headers=headers
    )

    assert response.status_code == 201
