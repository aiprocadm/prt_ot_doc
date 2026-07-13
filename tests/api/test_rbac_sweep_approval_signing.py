"""RBAC guards for the approval/signing route group (approval_signing_v1).

Security hardening sweep: the listed endpoints of ``approval_signing_v1`` were
protected only by tenant-scoping (``get_session`` + ``get_tenant_record``), so any
authenticated tenant user — including a rank-and-file ``worker`` — could start
approvals, request signatures, edit routes, and manage webhooks.

The router is mounted at ``/api/v1`` + router prefix ``/v1`` → paths are
``/api/v1/v1/...``. All listed endpoints share two dependencies:

* READ  (list/detail GETs): admin, owner, ot_pb_lead, ot_head, ot_specialist,
  pb_engineer, manager, line_manager, auditor_ro.
* WRITE (start/cancel/sign/routes/webhooks mutations): the READ set minus
  line_manager and auditor_ro.

Contract: worker → 403 FORBIDDEN on both read and write; ot_specialist (in both
sets) is allowed; line_manager is read-only and is forbidden on writes.
"""

from __future__ import annotations

import pytest

from app.models.models import RoleEnum

_WEBHOOK_BODY = {
    "event_type": "approval.completed",
    "url": "https://example.test/hook",
    "secret": "s3cr3t",
}


# --------------------------------------------------------------------------- #
# READ — GET /v1/approvals/processes
# --------------------------------------------------------------------------- #
@pytest.mark.anyio
async def test_approval_signing_read_forbidden_for_worker(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.WORKER)

    response = await async_client.get("/api/v1/v1/approvals/processes", headers=headers)

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


@pytest.mark.anyio
async def test_approval_signing_read_allowed_for_ot_specialist(
    async_client, make_auth_headers
) -> None:
    headers = await make_auth_headers(RoleEnum.OT_SPECIALIST)

    response = await async_client.get("/api/v1/v1/approvals/processes", headers=headers)

    assert response.status_code == 200


# --------------------------------------------------------------------------- #
# WRITE — POST /v1/webhooks
# --------------------------------------------------------------------------- #
@pytest.mark.anyio
async def test_approval_signing_write_forbidden_for_worker(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.WORKER)

    response = await async_client.post("/api/v1/v1/webhooks", json=_WEBHOOK_BODY, headers=headers)

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


@pytest.mark.anyio
async def test_approval_signing_write_forbidden_for_line_manager(
    async_client, make_auth_headers
) -> None:
    """line_manager may read the group but not mutate it (read/write split)."""
    headers = await make_auth_headers(RoleEnum.LINE_MANAGER)

    response = await async_client.post("/api/v1/v1/webhooks", json=_WEBHOOK_BODY, headers=headers)

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


@pytest.mark.anyio
async def test_approval_signing_write_allowed_for_ot_specialist(
    async_client, make_auth_headers
) -> None:
    headers = await make_auth_headers(RoleEnum.OT_SPECIALIST)

    response = await async_client.post("/api/v1/v1/webhooks", json=_WEBHOOK_BODY, headers=headers)

    assert response.status_code == 200
    assert response.json()["url"] == _WEBHOOK_BODY["url"]
