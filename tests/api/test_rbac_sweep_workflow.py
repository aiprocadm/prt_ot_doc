"""RBAC guards for the /workflow module (definitions / versions / instances / tasks).

Part of the systematic router RBAC sweep (docs/audit/RBAC_ROUTE_GROUP_AUDIT_2026-07-12.md).
Before this hardening every listed endpoint carried only ``Depends(rbac())`` with NO
required roles, so any authenticated tenant user — including a rank-and-file worker —
could read and mutate workflow config.

Role split for this module:
* READ  → admin, owner, ot_pb_lead, ot_head, ot_specialist, pb_engineer, manager,
  line_manager, auditor_ro
* WRITE → admin, owner, ot_pb_lead ONLY (workflow/process config is admin-grade — the
  write set is TIGHTER than the standard split, so ot_specialist/line_manager are
  read-only here).
"""

from __future__ import annotations

import pytest

from app.models.models import RoleEnum

# Pydantic-valid definition body. The graph is only inspected inside the service
# (after the RBAC guard runs), so for a forbidden actor the guard fires with 403
# before graph validation — but the body must still satisfy WorkflowDefinitionIn.
_VALID_GRAPH = {
    "nodes": [{"id": "s", "type": "start"}, {"id": "e", "type": "end"}],
    "transitions": [{"from": "s", "to": "e"}],
}
_DEFINITION_BODY = {
    "code": "rbac-sweep-def",
    "name": "RBAC Sweep Definition",
    "entity_type": "document",
    "graph": _VALID_GRAPH,
}


# --------------------------------------------------------------------------- #
# READ
# --------------------------------------------------------------------------- #
@pytest.mark.anyio
async def test_workflow_read_forbidden_for_worker(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.WORKER)

    response = await async_client.get("/api/v1/workflow/definitions", headers=headers)

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


@pytest.mark.anyio
async def test_workflow_read_allowed_for_ot_specialist(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.OT_SPECIALIST)

    response = await async_client.get("/api/v1/workflow/definitions", headers=headers)

    assert response.status_code == 200


# --------------------------------------------------------------------------- #
# WRITE (tighter set: admin / owner / ot_pb_lead only)
# --------------------------------------------------------------------------- #
@pytest.mark.anyio
async def test_workflow_write_forbidden_for_worker(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.WORKER)

    response = await async_client.post(
        "/api/v1/workflow/definitions", json=_DEFINITION_BODY, headers=headers
    )

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


@pytest.mark.anyio
async def test_workflow_write_forbidden_for_ot_specialist(async_client, make_auth_headers) -> None:
    """ot_specialist may READ workflow config but not WRITE it (tighter write split)."""
    headers = await make_auth_headers(RoleEnum.OT_SPECIALIST)

    response = await async_client.post(
        "/api/v1/workflow/definitions", json=_DEFINITION_BODY, headers=headers
    )

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


@pytest.mark.anyio
async def test_workflow_write_allowed_for_admin(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)

    response = await async_client.post(
        "/api/v1/workflow/definitions", json=_DEFINITION_BODY, headers=headers
    )

    assert response.status_code == 201
