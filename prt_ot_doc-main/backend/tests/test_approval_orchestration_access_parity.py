from app.api.routes.approval_orchestration import (
    _APPROVAL_ORCH_READ_ROLES,
    _APPROVAL_ORCH_WRITE_ROLES,
)


def test_approval_orchestration_write_roles_are_subset_of_read_roles() -> None:
    assert set(_APPROVAL_ORCH_WRITE_ROLES).issubset(set(_APPROVAL_ORCH_READ_ROLES))
