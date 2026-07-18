from __future__ import annotations

from app.api.routes.inspections import _INSPECTION_READ_ROLES, _INSPECTION_WRITE_ROLES


def test_inspections_access_roles_read_write_parity() -> None:
    read_roles = set(_INSPECTION_READ_ROLES)
    write_roles = set(_INSPECTION_WRITE_ROLES)

    # Any write-capable role must also be allowed to read inspection surfaces.
    assert write_roles.issubset(read_roles)
