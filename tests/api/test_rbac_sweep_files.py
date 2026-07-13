"""RBAC guard for the files module's ``POST /files/{file_id}:reindex`` endpoint.

Sweep follow-up (docs/audit/RBAC_ROUTE_GROUP_AUDIT_2026-07-12.md): every other
endpoint in ``app.modules.files.api`` already carried the tenant-scoped write
guard (``WRITE_ACCESS_DEP`` + ``_enforce_access_role(access, _FILE_UPLOAD_ROLES)``);
``:reindex`` was the lone gap — reachable by any authenticated tenant user,
including a rank-and-file ``worker``. This module uses its OWN role split
(``_FILE_UPLOAD_ROLES = ["admin", "employee"]``), so the allowed-role assertions
use ``employee``/``admin`` rather than the standard ``ot_specialist``.

Contract: worker → 403 FORBIDDEN; an allowed write role clears the guard and,
for a nonexistent file id, then falls through to 404 (not 403).
"""

from __future__ import annotations

import pytest

from app.models.models import RoleEnum

_REINDEX_PATH = "/api/v1/files/nonexistent-file:reindex"


@pytest.mark.anyio
async def test_files_reindex_forbidden_for_worker(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.WORKER)

    response = await async_client.post(_REINDEX_PATH, headers=headers)

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


@pytest.mark.anyio
async def test_files_reindex_forbidden_for_ot_specialist(async_client, make_auth_headers) -> None:
    """This module's write set is ["admin", "employee"] — ot_specialist is NOT in it."""
    headers = await make_auth_headers(RoleEnum.OT_SPECIALIST)

    response = await async_client.post(_REINDEX_PATH, headers=headers)

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


@pytest.mark.anyio
async def test_files_reindex_passes_guard_for_employee(async_client, make_auth_headers) -> None:
    """employee clears the write guard; a missing file then yields 404 (not 403)."""
    headers = await make_auth_headers(RoleEnum.EMPLOYEE)

    response = await async_client.post(_REINDEX_PATH, headers=headers)

    assert response.status_code == 404


@pytest.mark.anyio
async def test_files_reindex_passes_guard_for_admin(async_client, make_auth_headers) -> None:
    """admin clears the write guard; a missing file then yields 404 (not 403)."""
    headers = await make_auth_headers(RoleEnum.ADMIN)

    response = await async_client.post(_REINDEX_PATH, headers=headers)

    assert response.status_code == 404
