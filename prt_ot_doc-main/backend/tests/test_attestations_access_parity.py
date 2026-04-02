from __future__ import annotations

from app.api.routes.attestations import (
    _ATTESTATION_READ_ROLES,
    _ATTESTATION_WRITE_ROLES,
)


def test_attestations_access_roles_read_write_parity() -> None:
    read_roles = set(_ATTESTATION_READ_ROLES)
    write_roles = set(_ATTESTATION_WRITE_ROLES)

    # Any write-capable role must also be allowed to read attestation surfaces.
    assert write_roles.issubset(read_roles)
