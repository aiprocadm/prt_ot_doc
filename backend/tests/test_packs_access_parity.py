from __future__ import annotations

from app.api.routes.packs import _PACK_READ_ROLES, _PACK_WRITE_ROLES


def test_pack_access_roles_read_write_parity() -> None:
    read_roles = set(_PACK_READ_ROLES)
    write_roles = set(_PACK_WRITE_ROLES)

    # Any write-capable role must also be able to read pack data.
    assert write_roles.issubset(read_roles)

    # Client users can read pack surfaces but cannot run/manage packs.
    assert "client_user" in read_roles
    assert "client_user" not in write_roles
