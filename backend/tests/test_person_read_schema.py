from __future__ import annotations

from datetime import datetime
from uuid import UUID

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


def test_person_read_invalid_email_becomes_none() -> None:
    data = _base_person_payload()
    data["email"] = "not-an-email"
    model = PersonRead.model_validate(data)
    assert model.email is None


def test_person_read_coerces_qualification_kind_and_strips_bad_issuer() -> None:
    data = _base_person_payload()
    data["qualifications"] = [{"name": "Допуск", "kind": 99, "issuer": {"x": 1}}]
    model = PersonRead.model_validate(data)
    assert len(model.qualifications) == 1
    assert model.qualifications[0].kind == "99"
    assert model.qualifications[0].issuer is None


def test_person_read_truncates_long_qualification_name() -> None:
    data = _base_person_payload()
    long_name = "я" * 300
    data["qualifications"] = [{"name": long_name}]
    model = PersonRead.model_validate(data)
    assert len(model.qualifications) == 1
    assert len(model.qualifications[0].name) == 255


def test_person_read_coerces_ppe_status_from_number() -> None:
    data = _base_person_payload()
    data["current_ppe"] = [{"name": "Каска", "status": 1}]
    model = PersonRead.model_validate(data)
    assert model.current_ppe[0].status == "1"


def test_person_read_coerces_datetime_with_time_to_date() -> None:
    data = _base_person_payload()
    data["birth_date"] = datetime(2020, 6, 15, 14, 30, 0)
    data["hired_at"] = datetime(2021, 1, 10, 9, 0, 0)
    model = PersonRead.model_validate(data)
    assert model.birth_date.isoformat() == "2020-06-15"
    assert model.hired_at.isoformat() == "2021-01-10"


def test_person_read_coerces_uuid_objects_to_str() -> None:
    pid = UUID("33333333-3333-3333-3333-333333333333")
    cid = UUID("44444444-4444-4444-4444-444444444444")
    data = _base_person_payload()
    data["id"] = pid
    data["company_id"] = cid
    data["position_id"] = UUID("55555555-5555-5555-5555-555555555555")
    model = PersonRead.model_validate(data)
    assert model.id == str(pid)
    assert model.company_id == str(cid)
    assert model.position_id == "55555555-5555-5555-5555-555555555555"


def test_person_read_coerces_none_first_name_to_empty_string() -> None:
    data = _base_person_payload()
    data["first_name"] = None
    model = PersonRead.model_validate(data)
    assert model.first_name == ""
