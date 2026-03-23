from __future__ import annotations

from app.api.routes.prescriptions import (
    _PRESCRIPTION_READ_ROLES,
    _PRESCRIPTION_WRITE_ROLES,
)


def test_prescriptions_access_roles_read_write_parity() -> None:
    read_roles = set(_PRESCRIPTION_READ_ROLES)
    write_roles = set(_PRESCRIPTION_WRITE_ROLES)

    # Any write-capable role must also be allowed to read prescription surfaces.
    assert write_roles.issubset(read_roles)
