from __future__ import annotations

from app.api.routes.ppe import _PPE_READ_ROLES, _PPE_WRITE_ROLES


def test_ppe_access_roles_read_write_parity() -> None:
    read_roles = set(_PPE_READ_ROLES)
    write_roles = set(_PPE_WRITE_ROLES)

    # Any write-capable role must also be allowed to read PPE surfaces.
    assert write_roles.issubset(read_roles)
