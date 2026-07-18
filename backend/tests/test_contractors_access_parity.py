from __future__ import annotations

from app.api.routes.contractors import _CONTRACTOR_READ_ROLES, _CONTRACTOR_WRITE_ROLES


def test_contractors_write_roles_are_subset_of_read_roles() -> None:
    assert set(_CONTRACTOR_WRITE_ROLES).issubset(set(_CONTRACTOR_READ_ROLES))
