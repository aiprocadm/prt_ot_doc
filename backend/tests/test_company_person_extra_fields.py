"""cm01: schema round-trip для company.status/tags и person.position_title.

Поля раньше собирались фронтом, но не было в API-моделях (тихая потеря данных).
Здесь — что схемы их принимают/отдают и что CompanyRead устойчив к легаси-строкам
(status NOT NULL server_default 'active', tags NULL до бэкфилла приложением).
"""

from __future__ import annotations

from app.schemas.company import CompanyCreate, CompanyRead, CompanyUpdate
from app.schemas.person import PersonCreate, PersonRead, PersonUpdate


def test_company_create_carries_status_and_tags() -> None:
    c = CompanyCreate(name="ООО Тест", status="archived", tags=["vip", "север"])
    assert c.status == "archived"
    assert c.tags == ["vip", "север"]


def test_company_create_defaults_status_active_tags_empty() -> None:
    c = CompanyCreate(name="ООО Тест")
    assert c.status == "active"
    assert c.tags == []


def test_company_read_coerces_legacy_null_status_and_tags() -> None:
    r = CompanyRead.model_validate({"id": "c1", "name": "ООО", "status": None, "tags": None})
    assert r.status == "active"
    assert r.tags == []


def test_company_read_passthrough_status_tags() -> None:
    r = CompanyRead.model_validate({"id": "c1", "name": "ООО", "status": "draft", "tags": ["a"]})
    assert r.status == "draft"
    assert r.tags == ["a"]


def test_company_update_accepts_status_tags() -> None:
    dumped = CompanyUpdate(status="active", tags=[]).model_dump(exclude_unset=True)
    assert dumped["status"] == "active"
    assert dumped["tags"] == []


def test_person_create_and_read_position_title() -> None:
    p = PersonCreate(company_id="comp-1", first_name="Иван", last_name="Иванов", position_title="Слесарь")
    assert p.position_title == "Слесарь"
    r = PersonRead.model_validate(
        {"id": "p1", "company_id": "comp-1", "first_name": "Иван", "last_name": "Иванов", "position_title": "Слесарь"}
    )
    assert r.position_title == "Слесарь"


def test_person_update_accepts_position_title() -> None:
    assert PersonUpdate(position_title="Мастер").model_dump(exclude_unset=True)["position_title"] == "Мастер"
