"""RBAC guards for the *lax role granularity* deferrals of the router sweep.

Follow-up to commit 23ac1ce0 (the 12-router missing-auth sweep). These endpoints
already required authentication (``rbac()`` with an empty role list) but imposed
**no role restriction**, so any authenticated tenant user — including a rank-and-file
``worker`` — could perform tenant-wide config writes. Lower severity than the fixed
missing-auth holes (a valid token is required), so deferred out of that one-class PR
and closed here.

Contract mirrors ``tests/api/test_rbac_sweep_docgen.py`` / the reference
``test_analytics_exports_rbac.py``: forbidden role -> 403 ``{"code": "FORBIDDEN"}``;
allowed role -> not 403.

Role sets (mirror 618614d9):
* read  = MGMT_READ  (admin/owner/hr/line_manager/manager/ot_pb_lead/ot_head/
                      ot_specialist/pb_engineer/accountant/auditor_ro)
* write = DOC_WRITE  (admin/owner/ot_specialist)
* recompute = ADMIN_OWNER (admin/owner) — mirrors analytics ``/recompute``.

``RoleEnum.LINE_MANAGER`` is the "read-allowed but write-forbidden" probe;
``RoleEnum.OT_SPECIALIST`` is allowed for both writes and reads.

The final section asserts the *deliberately un-gated* self-scoped views stay open to
a worker — a regression guard that the least-privilege pass did not over-reach.
"""

from __future__ import annotations

import pytest

from app.models.models import RoleEnum

_FAKE_ID = "00000000-0000-0000-0000-000000000000"

_WF_GRAPH = {
    "nodes": [
        {"id": "start", "type": "start", "name": "Start"},
        {"id": "end", "type": "end", "name": "End"},
    ],
    "transitions": [{"from": "start", "to": "end"}],
}


def _wf_definition_payload(code: str) -> dict:
    return {
        "code": code,
        "name": "RBAC probe",
        "entity_type": "document",
        "graph": _WF_GRAPH,
        "variables_schema": {},
    }


# ---------------------------------------------------------------- notifications templates


@pytest.mark.anyio
async def test_notification_templates_read_forbidden_for_worker(
    async_client, make_auth_headers
) -> None:
    headers = await make_auth_headers(RoleEnum.WORKER)
    response = await async_client.get("/api/v1/notifications/templates", headers=headers)
    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


@pytest.mark.anyio
async def test_notification_templates_read_allowed_for_line_manager(
    async_client, make_auth_headers
) -> None:
    headers = await make_auth_headers(RoleEnum.LINE_MANAGER)
    response = await async_client.get("/api/v1/notifications/templates", headers=headers)
    assert response.status_code != 403


@pytest.mark.anyio
async def test_notification_templates_write_forbidden_for_line_manager(
    async_client, make_auth_headers
) -> None:
    headers = await make_auth_headers(RoleEnum.LINE_MANAGER)
    response = await async_client.post(
        "/api/v1/notifications/templates",
        json={"channel": "email", "type": "generic", "subject": "s", "body": "b"},
        headers=headers,
    )
    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


@pytest.mark.anyio
async def test_notification_templates_write_allowed_for_ot_specialist(
    async_client, make_auth_headers
) -> None:
    headers = await make_auth_headers(RoleEnum.OT_SPECIALIST)
    response = await async_client.post(
        "/api/v1/notifications/templates",
        json={"channel": "email", "type": "generic", "subject": "s", "body": "b"},
        headers=headers,
    )
    assert response.status_code != 403


# ---------------------------------------------------------------- npa impact tasks


@pytest.mark.anyio
async def test_npa_impact_tasks_forbidden_for_worker(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.WORKER)
    response = await async_client.post(f"/api/v1/npa/{_FAKE_ID}/impact/tasks", headers=headers)
    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


@pytest.mark.anyio
async def test_npa_impact_tasks_forbidden_for_line_manager(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.LINE_MANAGER)
    response = await async_client.post(f"/api/v1/npa/{_FAKE_ID}/impact/tasks", headers=headers)
    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


@pytest.mark.anyio
async def test_npa_impact_tasks_allowed_for_ot_specialist(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.OT_SPECIALIST)
    response = await async_client.post(f"/api/v1/npa/{_FAKE_ID}/impact/tasks", headers=headers)
    assert response.status_code != 403


# ---------------------------------------------------------------- compliance recompute


@pytest.mark.anyio
async def test_compliance_recompute_forbidden_for_worker(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.WORKER)
    response = await async_client.post("/api/v1/compliance/deadlines/recompute", headers=headers)
    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


@pytest.mark.anyio
async def test_compliance_recompute_forbidden_for_line_manager(
    async_client, make_auth_headers
) -> None:
    """recompute is admin/owner only — a management role short of that is still 403."""
    headers = await make_auth_headers(RoleEnum.LINE_MANAGER)
    response = await async_client.post("/api/v1/compliance/deadlines/recompute", headers=headers)
    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


@pytest.mark.anyio
async def test_compliance_recompute_allowed_for_admin(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)
    response = await async_client.post("/api/v1/compliance/deadlines/recompute", headers=headers)
    assert response.status_code != 403


# ---------------------------------------------------------------- compliance reads
# The two GET reads expose tenant-wide workforce compliance data (per-person deadline
# status). Role-less like recompute was, so a rank-and-file ``worker`` could enumerate
# every person's compliance standing. Gate with MGMT_READ (read = management/HR/specialist
# set, mirrors branding/analytics). The audit listed only ``persons/{id}/summary``; the
# sibling ``GET /deadlines`` is the same sensitivity and root cause, so both are closed.


@pytest.mark.anyio
async def test_compliance_deadlines_read_forbidden_for_worker(
    async_client, make_auth_headers
) -> None:
    headers = await make_auth_headers(RoleEnum.WORKER)
    response = await async_client.get("/api/v1/compliance/deadlines", headers=headers)
    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


@pytest.mark.anyio
async def test_compliance_deadlines_read_allowed_for_line_manager(
    async_client, make_auth_headers
) -> None:
    headers = await make_auth_headers(RoleEnum.LINE_MANAGER)
    response = await async_client.get("/api/v1/compliance/deadlines", headers=headers)
    assert response.status_code != 403


@pytest.mark.anyio
async def test_compliance_person_summary_read_forbidden_for_worker(
    async_client, make_auth_headers
) -> None:
    headers = await make_auth_headers(RoleEnum.WORKER)
    response = await async_client.get(
        f"/api/v1/compliance/persons/{_FAKE_ID}/summary", headers=headers
    )
    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


@pytest.mark.anyio
async def test_compliance_person_summary_read_allowed_for_line_manager(
    async_client, make_auth_headers
) -> None:
    headers = await make_auth_headers(RoleEnum.LINE_MANAGER)
    response = await async_client.get(
        f"/api/v1/compliance/persons/{_FAKE_ID}/summary", headers=headers
    )
    assert response.status_code != 403


# ---------------------------------------------------------------- headers / layout presets


@pytest.mark.anyio
async def test_layout_presets_read_forbidden_for_worker(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.WORKER)
    response = await async_client.get("/api/v1/layout-presets", headers=headers)
    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


@pytest.mark.anyio
async def test_layout_presets_read_allowed_for_line_manager(
    async_client, make_auth_headers
) -> None:
    headers = await make_auth_headers(RoleEnum.LINE_MANAGER)
    response = await async_client.get("/api/v1/layout-presets", headers=headers)
    assert response.status_code != 403


@pytest.mark.anyio
async def test_layout_presets_write_forbidden_for_line_manager(
    async_client, make_auth_headers
) -> None:
    headers = await make_auth_headers(RoleEnum.LINE_MANAGER)
    response = await async_client.delete(f"/api/v1/layout-presets/{_FAKE_ID}", headers=headers)
    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


@pytest.mark.anyio
async def test_layout_presets_write_allowed_for_ot_specialist(
    async_client, make_auth_headers
) -> None:
    headers = await make_auth_headers(RoleEnum.OT_SPECIALIST)
    response = await async_client.delete(f"/api/v1/layout-presets/{_FAKE_ID}", headers=headers)
    assert response.status_code != 403


@pytest.mark.anyio
async def test_apply_headers_forbidden_for_worker(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.WORKER)
    response = await async_client.post(
        f"/api/v1/documents/{_FAKE_ID}/apply-headers",
        json={"preset_code": "default"},
        headers=headers,
    )
    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


@pytest.mark.anyio
async def test_apply_headers_allowed_for_ot_specialist(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.OT_SPECIALIST)
    response = await async_client.post(
        f"/api/v1/documents/{_FAKE_ID}/apply-headers",
        json={"preset_code": "default"},
        headers=headers,
    )
    assert response.status_code != 403


# ---------------------------------------------------------------- workflow definition/instance writes


@pytest.mark.anyio
async def test_workflow_definition_write_forbidden_for_worker(
    async_client, make_auth_headers
) -> None:
    headers = await make_auth_headers(RoleEnum.WORKER)
    response = await async_client.post(
        "/api/v1/workflow/definitions",
        json=_wf_definition_payload("rbac-probe-worker"),
        headers=headers,
    )
    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


@pytest.mark.anyio
async def test_workflow_definition_write_forbidden_for_line_manager(
    async_client, make_auth_headers
) -> None:
    headers = await make_auth_headers(RoleEnum.LINE_MANAGER)
    response = await async_client.post(
        "/api/v1/workflow/definitions",
        json=_wf_definition_payload("rbac-probe-lm"),
        headers=headers,
    )
    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


@pytest.mark.anyio
async def test_workflow_definition_write_allowed_for_ot_specialist(
    async_client, make_auth_headers
) -> None:
    headers = await make_auth_headers(RoleEnum.OT_SPECIALIST)
    response = await async_client.post(
        "/api/v1/workflow/definitions",
        json=_wf_definition_payload("rbac-probe-spec"),
        headers=headers,
    )
    assert response.status_code != 403


@pytest.mark.anyio
async def test_workflow_instance_write_forbidden_for_worker(
    async_client, make_auth_headers
) -> None:
    headers = await make_auth_headers(RoleEnum.WORKER)
    response = await async_client.post(
        "/api/v1/workflow/instances",
        json={"definition_code": "any", "entity_type": "document", "entity_id": "x", "context": {}},
        headers=headers,
    )
    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


@pytest.mark.anyio
async def test_workflow_instance_write_allowed_for_ot_specialist(
    async_client, make_auth_headers
) -> None:
    headers = await make_auth_headers(RoleEnum.OT_SPECIALIST)
    response = await async_client.post(
        "/api/v1/workflow/instances",
        json={"definition_code": "any", "entity_type": "document", "entity_id": "x", "context": {}},
        headers=headers,
    )
    assert response.status_code != 403


# --------------------------------------------------- deliberately un-gated (self-scoped) views
# Regression guard: the least-privilege pass must NOT gate per-user views a worker relies on.


@pytest.mark.anyio
async def test_workflow_tasks_stays_open_for_worker(async_client, make_auth_headers) -> None:
    """`GET /workflow/tasks` is self-scoped (assignee=me) and loaded on every page —
    a worker must keep access; in-service role checks guard task *actions*, not the list."""
    headers = await make_auth_headers(RoleEnum.WORKER)
    response = await async_client.get("/api/v1/workflow/tasks", headers=headers)
    assert response.status_code != 403


@pytest.mark.anyio
async def test_notifications_list_stays_open_for_worker(async_client, make_auth_headers) -> None:
    """`GET /notifications` is the caller's own inbox (scoped by user_id) — not gated."""
    headers = await make_auth_headers(RoleEnum.WORKER)
    response = await async_client.get("/api/v1/notifications", headers=headers)
    assert response.status_code != 403
