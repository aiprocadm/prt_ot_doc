from __future__ import annotations

from app.models.models import EmploymentStatus
from app.schemas.person import PersonRead


def _base_person_payload() -> dict:
    return {
        "id": "11111111-1111-1111-1111-111111111111",
        "company_id": "22222222-2222-2222-2222-222222222222",
        "first_name": "Иван",
        "last_name": "Иванов",
        "employment_status": EmploymentStatus.ACTIVE,
        "qualifications": [],
        "current_ppe": [],
        "hazardous_factors": [],
    }


def test_person_read_accepts_blank_email_as_none() -> None:
    data = _base_person_payload()
    data["email"] = ""
    model = PersonRead.model_validate(data)
    assert model.email is None


def test_person_read_drops_qualification_rows_without_name() -> None:
    data = _base_person_payload()
    data["qualifications"] = [{}, {"name": "  Допуск  ", "kind": ""}]
    model = PersonRead.model_validate(data)
    assert len(model.qualifications) == 1
    assert model.qualifications[0].name == "Допуск"
    assert model.qualifications[0].kind == "training"


def test_person_read_drops_ppe_rows_without_name() -> None:
    data = _base_person_payload()
    data["current_ppe"] = [{}, {"name": "Каска"}]
    model = PersonRead.model_validate(data)
    assert len(model.current_ppe) == 1
    assert model.current_ppe[0].name == "Каска"
