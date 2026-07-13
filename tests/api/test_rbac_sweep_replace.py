"""RBAC guards for the ``replace`` router (find/replace maps + runs).

Part of the systematic route-group RBAC audit
(docs/audit/RBAC_ROUTE_GROUP_AUDIT_2026-07-12.md). The replace endpoints were
protected only by tenant-scoping (``get_session`` + ``get_tenant_record``), so
any authenticated tenant user — including a rank-and-file ``worker`` — could
list/manage replace maps and execute :dry-run / :apply / rollback mutations.

Contract now:
* READ  (GET replace-maps, replace-runs/{id}, /report, /report.csv) → worker 403,
  ot_specialist 200.
* WRITE  (replace-maps CRUD, :dry-run, :apply, rollback) → worker 403;
  line_manager (read-only in this split) 403; ot_specialist clears the guard.

All listed endpoints share the same two access deps, so a representative
sample proves the contract.
"""

from __future__ import annotations

import pytest

from app.models.models import RoleEnum


# --------------------------------------------------------------------------- #
# READ — GET /replace-maps
# --------------------------------------------------------------------------- #
@pytest.mark.anyio
async def test_replace_read_forbidden_for_worker(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.WORKER)

    response = await async_client.get("/api/v1/replace-maps", headers=headers)

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


@pytest.mark.anyio
async def test_replace_read_allowed_for_ot_specialist(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.OT_SPECIALIST)

    response = await async_client.get("/api/v1/replace-maps", headers=headers)

    assert response.status_code == 200


# --------------------------------------------------------------------------- #
# WRITE — POST /replace-maps (create); worker forbidden
# --------------------------------------------------------------------------- #
@pytest.mark.anyio
async def test_replace_write_forbidden_for_worker(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.WORKER)

    # Form fields are optional; the guard fires before body handling, so an
    # empty POST yields 403 (guard), not 400 (missing payload).
    response = await async_client.post("/api/v1/replace-maps", headers=headers)

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


# --------------------------------------------------------------------------- #
# WRITE — rollback (:apply-family action POST); read/write split + guard-clears
# --------------------------------------------------------------------------- #
@pytest.mark.anyio
async def test_replace_rollback_forbidden_for_line_manager(async_client, make_auth_headers) -> None:
    """line_manager may read replace data but not execute a rollback (write)."""
    headers = await make_auth_headers(RoleEnum.LINE_MANAGER)

    response = await async_client.post(
        "/api/v1/replace-runs/some-run/rollback", json={}, headers=headers
    )

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


@pytest.mark.anyio
async def test_replace_rollback_passes_guard_for_ot_specialist(
    async_client, make_auth_headers
) -> None:
    """ot_specialist clears the write guard; a missing/invalid run then yields 400."""
    headers = await make_auth_headers(RoleEnum.OT_SPECIALIST)

    response = await async_client.post(
        "/api/v1/replace-runs/nonexistent-run/rollback", json={}, headers=headers
    )

    assert response.status_code != 403
    assert response.status_code == 400
