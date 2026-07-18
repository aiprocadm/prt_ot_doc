from __future__ import annotations

from app.api.routes.files import _FILE_READ_ROLES, _FILE_UPLOAD_ROLES


def test_files_access_roles_read_write_parity() -> None:
    read_roles = set(_FILE_READ_ROLES)
    write_roles = set(_FILE_UPLOAD_ROLES)

    # Any upload-capable role must also be able to read file surfaces.
    assert write_roles.issubset(read_roles)

    # Client portal roles can read files but cannot upload them.
    assert "client_user" in read_roles
    assert "client_user" not in write_roles
