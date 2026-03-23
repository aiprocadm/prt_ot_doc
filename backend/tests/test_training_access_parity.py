from __future__ import annotations

from app.api.routes.training import _TRAINING_READ_ROLES, _TRAINING_WRITE_ROLES


def test_training_access_roles_read_write_parity() -> None:
    read_roles = set(_TRAINING_READ_ROLES)
    write_roles = set(_TRAINING_WRITE_ROLES)

    # Any write-capable role must also be allowed to read training surfaces.
    assert write_roles.issubset(read_roles)
