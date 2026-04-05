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


def test_person_read_coerces_hazardous_factors_to_strings() -> None:
    data = _base_person_payload()
    data["hazardous_factors"] = [1, "  шум  ", None, {"x": 1}, []]
    model = PersonRead.model_validate(data)
    assert model.hazardous_factors == ["1", "шум"]


def test_person_read_strips_invalid_qualification_dates() -> None:
    data = _base_person_payload()
    data["qualifications"] = [
        {"name": "Допуск", "issued_at": "notadate", "valid_until": "2020-01-02"},
    ]
    model = PersonRead.model_validate(data)
    assert len(model.qualifications) == 1
    assert model.qualifications[0].issued_at is None
    assert model.qualifications[0].valid_until.isoformat() == "2020-01-02"


def test_person_read_coerces_unknown_employment_status() -> None:
    data = _base_person_payload()
    data["employment_status"] = "weird"
    model = PersonRead.model_validate(data)
    assert model.employment_status == EmploymentStatus.ACTIVE
