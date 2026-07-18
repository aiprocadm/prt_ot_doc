from __future__ import annotations

from app.api.routes.persons import _PERSON_READ_ROLES, _PERSON_WRITE_ROLES


def test_persons_access_roles_read_write_parity() -> None:
    read_roles = set(_PERSON_READ_ROLES)
    write_roles = set(_PERSON_WRITE_ROLES)

    # Any write-capable role must also be allowed to read person surfaces.
    assert write_roles.issubset(read_roles)
