"""RBAC guards for the /branding router (white-label config).

Before the sweep the branding endpoints were protected only by
get_session + get_tenant_record, so any authenticated tenant user —
including a rank-and-file 'worker' — could read the white-label profile
and drive letterhead previews. This pins the contract:

* reads (GET /branding/profile, GET /branding/history) require a read role;
* writes (PATCH /branding/profile/{company_id}, POST /branding/preview)
  require the stricter write role set (line_manager / auditor_ro are
  read-only and must be rejected on writes).

worker is outside both sets → 403 FORBIDDEN everywhere.
"""

from __future__ import annotations

import pytest

from app.models.models import RoleEnum


@pytest.mark.anyio
async def test_branding_read_forbidden_for_worker(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.WORKER)

    response = await async_client.get(
        "/api/v1/branding/profile", params={"company_id": "does-not-exist"}, headers=headers
    )

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


@pytest.mark.anyio
async def test_branding_read_allowed_for_ot_specialist(async_client, make_auth_headers) -> None:
    """ot_specialist is in the read set: the guard admits the request.

    No company is seeded for the fabricated id, so the handler resolves to
    404 (Company not found) — the point is that it is *not* a 403 from the
    RBAC guard.
    """
    headers = await make_auth_headers(RoleEnum.OT_SPECIALIST)

    response = await async_client.get(
        "/api/v1/branding/profile", params={"company_id": "does-not-exist"}, headers=headers
    )

    assert response.status_code != 403


@pytest.mark.anyio
async def test_branding_write_forbidden_for_worker(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.WORKER)

    response = await async_client.post(
        "/api/v1/branding/preview",
        json={"company_id": "does-not-exist"},
        headers=headers,
    )

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


@pytest.mark.anyio
async def test_branding_write_forbidden_for_read_only_role(async_client, make_auth_headers) -> None:
    """line_manager can read branding but is outside the write set."""
    headers = await make_auth_headers(RoleEnum.LINE_MANAGER)

    response = await async_client.post(
        "/api/v1/branding/preview",
        json={"company_id": "does-not-exist"},
        headers=headers,
    )

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"
