from __future__ import annotations

from app.api.routes.incidents import _INCIDENT_READ_ROLES, _INCIDENT_WRITE_ROLES


def test_incidents_access_roles_read_write_parity() -> None:
    read_roles = set(_INCIDENT_READ_ROLES)
    write_roles = set(_INCIDENT_WRITE_ROLES)

    # Any write-capable role must also be allowed to read incident surfaces.
    assert write_roles.issubset(read_roles)
