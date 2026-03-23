from __future__ import annotations

from app.api.routes.safety_ops import _EDITOR_ROLES, _MANAGER_ROLES


def test_safety_ops_access_roles_read_write_parity() -> None:
    read_roles = set(_MANAGER_ROLES)
    write_roles = set(_EDITOR_ROLES)

    # Any write-capable role must also be allowed to read safety operations surfaces.
    assert write_roles.issubset(read_roles)
