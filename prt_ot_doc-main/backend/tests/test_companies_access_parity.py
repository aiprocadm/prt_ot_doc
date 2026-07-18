from __future__ import annotations

from app.api.routes.companies import _COMPANY_READ_ROLES, _COMPANY_WRITE_ROLES


def test_companies_access_roles_read_write_parity() -> None:
    read_roles = set(_COMPANY_READ_ROLES)
    write_roles = set(_COMPANY_WRITE_ROLES)

    # Any write-capable role must also be allowed to read company surfaces.
    assert write_roles.issubset(read_roles)
