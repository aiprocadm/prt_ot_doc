"""RBAC guard for the approval-signing v1 router (sweep row 3).

api/routes/approval_signing_v1.py (mounted at /api/v1/v1) had NO rbac/abac on any
of its ~30 endpoints. Its bespoke `_approval_signing_forbidden` check only compared
`task.assignee_id` to the attacker-controlled `X-User-Id` header, so it was trivially
bypassable and provided no real authn/authz. The router is now guarded at router
level with abac(APPROVAL_ROLES = admin/employee), mirroring approval_orchestration.
"""

from __future__ import annotations

import pytest

from app.models.models import RoleEnum

_FAKE_ID = "00000000-0000-0000-0000-000000000000"
_BASE = "/api/v1/v1"


@pytest.mark.anyio
async def test_approvals_processes_forbidden_for_worker(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.WORKER)
    response = await async_client.get(f"{_BASE}/approvals/processes", headers=headers)
    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


@pytest.mark.anyio
async def test_approvals_processes_allowed_for_employee(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.EMPLOYEE)
    response = await async_client.get(f"{_BASE}/approvals/processes", headers=headers)
    assert response.status_code != 403


@pytest.mark.anyio
async def test_approvals_start_forbidden_for_worker(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.WORKER)
    response = await async_client.post(f"{_BASE}/approvals:start", json={}, headers=headers)
    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


@pytest.mark.anyio
async def test_approvals_start_allowed_for_admin(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)
    response = await async_client.post(f"{_BASE}/approvals:start", json={}, headers=headers)
    assert response.status_code != 403


@pytest.mark.anyio
async def test_webhook_create_forbidden_for_worker(async_client, make_auth_headers) -> None:
    """Creating a webhook endpoint (attacker-chosen URL+secret) must be rejected."""
    headers = await make_auth_headers(RoleEnum.WORKER)
    response = await async_client.post(f"{_BASE}/webhooks", json={}, headers=headers)
    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"
