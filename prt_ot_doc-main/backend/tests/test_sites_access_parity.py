from __future__ import annotations

from app.api.routes.sites import _SITE_READ_ROLES, _SITE_WRITE_ROLES


def test_sites_access_roles_read_write_parity() -> None:
    read_roles = set(_SITE_READ_ROLES)
    write_roles = set(_SITE_WRITE_ROLES)

    # Any write-capable role must also be allowed to read site/workplace surfaces.
    assert write_roles.issubset(read_roles)
