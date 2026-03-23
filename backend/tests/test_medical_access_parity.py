from app.api.routes.medical import _MEDICAL_READ_ROLES, _MEDICAL_WRITE_ROLES


def test_medical_write_roles_are_subset_of_read_roles() -> None:
    assert set(_MEDICAL_WRITE_ROLES).issubset(set(_MEDICAL_READ_ROLES))
