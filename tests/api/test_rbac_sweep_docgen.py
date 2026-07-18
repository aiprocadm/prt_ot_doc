"""RBAC guards for document-generation modules (RBAC router sweep, rows 5-8).

Follow-up to commit 618614d9 (analytics/exports). The branding / replace / packs
(packs_v2) / pipelines routers were protected only by get_session +
get_tenant_record — i.e. reachable by any role (effectively without a valid token,
just a tenant slug). Contract mirrors tests/api/test_analytics_exports_rbac.py:
forbidden role -> 403 {"code": "FORBIDDEN"}; allowed role -> not 403.

Role sets (mirror 618614d9):
* read  = MGMT_READ  (admin/owner/hr/line_manager/manager/ot_pb_lead/ot_head/
                      ot_specialist/pb_engineer/accountant/auditor_ro)
* write = DOC_WRITE  (admin/owner/ot_specialist)

RoleEnum.LINE_MANAGER is the "read-allowed but write-forbidden" probe;
RoleEnum.OT_SPECIALIST is allowed for both.
"""

from __future__ import annotations

import pytest

from app.models.models import RoleEnum

_FAKE_ID = "00000000-0000-0000-0000-000000000000"


# ---------------------------------------------------------------- branding


@pytest.mark.anyio
async def test_branding_read_forbidden_for_worker(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.WORKER)
    response = await async_client.get(
        f"/api/v1/branding/profile?company_id={_FAKE_ID}", headers=headers
    )
    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


@pytest.mark.anyio
async def test_branding_read_allowed_for_ot_specialist(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.OT_SPECIALIST)
    response = await async_client.get(
        f"/api/v1/branding/profile?company_id={_FAKE_ID}", headers=headers
    )
    assert response.status_code != 403


@pytest.mark.anyio
async def test_branding_write_forbidden_for_line_manager(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.LINE_MANAGER)
    response = await async_client.patch(
        f"/api/v1/branding/profile/{_FAKE_ID}", json={"branding": {}}, headers=headers
    )
    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


# ---------------------------------------------------------------- replace


@pytest.mark.anyio
async def test_replace_read_forbidden_for_worker(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.WORKER)
    response = await async_client.get("/api/v1/replace-maps", headers=headers)
    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


@pytest.mark.anyio
async def test_replace_read_allowed_for_line_manager(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.LINE_MANAGER)
    response = await async_client.get("/api/v1/replace-maps", headers=headers)
    assert response.status_code == 200


@pytest.mark.anyio
async def test_replace_write_forbidden_for_line_manager(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.LINE_MANAGER)
    response = await async_client.delete(f"/api/v1/replace-maps/{_FAKE_ID}", headers=headers)
    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


@pytest.mark.anyio
async def test_replace_write_allowed_for_ot_specialist(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.OT_SPECIALIST)
    response = await async_client.delete(f"/api/v1/replace-maps/{_FAKE_ID}", headers=headers)
    assert response.status_code != 403


# ---------------------------------------------------------------- packs (packs_v2)


@pytest.mark.anyio
async def test_packs_read_forbidden_for_worker(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.WORKER)
    response = await async_client.get("/api/v1/package-profiles", headers=headers)
    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


@pytest.mark.anyio
async def test_packs_read_allowed_for_line_manager(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.LINE_MANAGER)
    response = await async_client.get("/api/v1/package-profiles", headers=headers)
    assert response.status_code == 200


@pytest.mark.anyio
async def test_packs_write_forbidden_for_line_manager(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.LINE_MANAGER)
    response = await async_client.delete(f"/api/v1/package-profiles/{_FAKE_ID}", headers=headers)
    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


@pytest.mark.anyio
async def test_packs_write_allowed_for_ot_specialist(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.OT_SPECIALIST)
    response = await async_client.delete(f"/api/v1/package-profiles/{_FAKE_ID}", headers=headers)
    assert response.status_code != 403


# ---------------------------------------------------------------- pipelines


@pytest.mark.anyio
async def test_pipelines_read_forbidden_for_worker(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.WORKER)
    response = await async_client.get("/api/v1/pipelines/profiles", headers=headers)
    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


@pytest.mark.anyio
async def test_pipelines_read_allowed_for_line_manager(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.LINE_MANAGER)
    response = await async_client.get("/api/v1/pipelines/profiles", headers=headers)
    assert response.status_code == 200


@pytest.mark.anyio
async def test_pipelines_write_forbidden_for_line_manager(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.LINE_MANAGER)
    response = await async_client.delete(f"/api/v1/pipelines/profiles/{_FAKE_ID}", headers=headers)
    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


@pytest.mark.anyio
async def test_pipelines_write_allowed_for_ot_specialist(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.OT_SPECIALIST)
    response = await async_client.delete(f"/api/v1/pipelines/profiles/{_FAKE_ID}", headers=headers)
    assert response.status_code != 403
