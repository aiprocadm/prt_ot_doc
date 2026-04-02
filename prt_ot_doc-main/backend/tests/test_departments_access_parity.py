from __future__ import annotations

from app.api.routes.departments import _DEPARTMENT_READ_ROLES, _DEPARTMENT_WRITE_ROLES


def test_departments_access_roles_read_write_parity() -> None:
    read_roles = set(_DEPARTMENT_READ_ROLES)
    write_roles = set(_DEPARTMENT_WRITE_ROLES)

    # Any write-capable role must also be allowed to read department surfaces.
    assert write_roles.issubset(read_roles)
