from __future__ import annotations

from app.api.routes.contracts import _CONTRACT_READ_ROLES, _CONTRACT_WRITE_ROLES


def test_contracts_access_roles_read_write_parity() -> None:
    read_roles = set(_CONTRACT_READ_ROLES)
    write_roles = set(_CONTRACT_WRITE_ROLES)

    # Any write-capable role must also be allowed to read contract surfaces.
    assert write_roles.issubset(read_roles)
