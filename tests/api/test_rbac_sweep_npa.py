"""RBAC guard for the npa router's single write gap.

Part of the systematic RBAC route-group sweep
(docs/audit/RBAC_ROUTE_GROUP_AUDIT_2026-07-12.md). The npa reads
(``GET /npa`` / ``GET /npa/{act_id}``) are intentionally auth-only, but
``POST /npa/{act_id}/impact/tasks`` mutates the legal/planning domain by
creating update tasks and was only tenant-scoped (roleless ``rbac()``), so any
authenticated tenant user — including a rank-and-file worker — could trigger it.

Contract for the write endpoint: worker → 403, read-only line_manager → 403,
and the OT/PB management roles plus ``lawyer`` (legal domain) clear the guard.
A nonexistent act clears the guard and yields 200 (``created: 0``), proving a
403 comes from the role guard rather than validation.
"""

from __future__ import annotations

import pytest

from app.models.models import RoleEnum

_WRITE_PATH = "/api/v1/npa/nonexistent-act/impact/tasks"


@pytest.mark.anyio
async def test_npa_impact_tasks_forbidden_for_worker(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.WORKER)

    response = await async_client.post(_WRITE_PATH, headers=headers)

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


@pytest.mark.anyio
async def test_npa_impact_tasks_forbidden_for_line_manager(async_client, make_auth_headers) -> None:
    """line_manager is read-only in the standard split — not in the npa write set."""
    headers = await make_auth_headers(RoleEnum.LINE_MANAGER)

    response = await async_client.post(_WRITE_PATH, headers=headers)

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


@pytest.mark.anyio
async def test_npa_impact_tasks_allowed_for_ot_specialist(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.OT_SPECIALIST)

    response = await async_client.post(_WRITE_PATH, headers=headers)

    assert response.status_code == 200
    assert response.json()["created"] == 0


@pytest.mark.anyio
async def test_npa_impact_tasks_allowed_for_lawyer(async_client, make_auth_headers) -> None:
    """lawyer is explicitly included because npa impact is a legal-domain write."""
    headers = await make_auth_headers(RoleEnum.LAWYER)

    response = await async_client.post(_WRITE_PATH, headers=headers)

    assert response.status_code == 200
    assert response.json()["created"] == 0
