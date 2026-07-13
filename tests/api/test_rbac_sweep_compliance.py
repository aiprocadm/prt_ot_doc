"""RBAC guard contract for the /compliance router (sweep).

The two role-less endpoints closed here were previously reachable by any
authenticated tenant user (``rbac()`` with no required roles):

* ``POST /compliance/deadlines/recompute`` — bulk mutation → WRITE
  (admin/owner/ot_pb_lead/ot_specialist).
* ``GET /compliance/persons/{person_id}/summary`` — READ.
"""

from __future__ import annotations

import pytest

from app.models.models import RoleEnum


@pytest.mark.anyio
async def test_compliance_read_forbidden_for_worker(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.WORKER)

    response = await async_client.get(
        "/api/v1/compliance/persons/some-person/summary", headers=headers
    )

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


@pytest.mark.anyio
async def test_compliance_read_allowed_for_ot_specialist(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.OT_SPECIALIST)

    response = await async_client.get(
        "/api/v1/compliance/persons/some-person/summary", headers=headers
    )

    assert response.status_code == 200


@pytest.mark.anyio
async def test_compliance_write_forbidden_for_worker(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.WORKER)

    response = await async_client.post("/api/v1/compliance/deadlines/recompute", headers=headers)

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


@pytest.mark.anyio
async def test_compliance_write_forbidden_for_line_manager(async_client, make_auth_headers) -> None:
    """line_manager may read compliance but not run the bulk recompute (read/write split)."""
    headers = await make_auth_headers(RoleEnum.LINE_MANAGER)

    response = await async_client.post("/api/v1/compliance/deadlines/recompute", headers=headers)

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


@pytest.mark.anyio
async def test_compliance_write_allowed_for_ot_specialist(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.OT_SPECIALIST)

    response = await async_client.post("/api/v1/compliance/deadlines/recompute", headers=headers)

    assert response.status_code == 200
