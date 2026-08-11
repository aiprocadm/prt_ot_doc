from __future__ import annotations

from app.api.routes.external_registry import (
    _EXTERNAL_REGISTRY_READ_ROLES,
    _EXTERNAL_REGISTRY_WRITE_ROLES,
)


def test_external_registry_access_roles_read_write_parity() -> None:
    read_roles = set(_EXTERNAL_REGISTRY_READ_ROLES)
    write_roles = set(_EXTERNAL_REGISTRY_WRITE_ROLES)

    assert write_roles.issubset(read_roles)
    assert "integrations" in read_roles
