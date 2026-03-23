from __future__ import annotations

from app.api.routes.tasks import _TASK_READ_ROLES, _TASK_WRITE_ROLES


def test_tasks_access_roles_read_write_parity() -> None:
    read_roles = set(_TASK_READ_ROLES)
    write_roles = set(_TASK_WRITE_ROLES)

    # Any write-capable role must also be allowed to read task surfaces.
    assert write_roles.issubset(read_roles)

    # Worker role has read access but no write permissions.
    assert "worker" in read_roles
    assert "worker" not in write_roles
