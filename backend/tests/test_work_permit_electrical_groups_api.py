"""Task 2 — интеграционные тесты обогащения электронаряда группами 903н.

Тест работает без реальной БД: _permit_read и list_members патчатся через AsyncMock,
Person-запрос — через session.execute mock. Паттерн мока: строим мок-объект wp + members
с нужными атрибутами и патчим зависимости на уровне модуля routes.work_permits.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.work_permit import WorkPermitRead, WorkPermitMemberRead


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_wp(work_type: str = "electrical") -> SimpleNamespace:
    """Фиктивный WorkPermit-объект с минимальным набором атрибутов."""
    now = datetime(2026, 6, 23, 10, 0, 0, tzinfo=timezone.utc)
    return SimpleNamespace(
        id=uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        number="WP-001",
        work_type=work_type,
        zone_text="РУ-6 кВ, ячейка №7",
        site_id=None,
        equipment_text=None,
        hazards_text=None,
        measures_text=None,
        planned_start=None,
        planned_end=None,
        status="draft",
        opened_at=None,
        closed_at=None,
        suspended_at=None,
        subdivision_text=None,
        content_text=None,
        conditions_text=None,
        safety_systems=None,
        measures_before_text=None,
        measures_during_text=None,
        special_conditions_text=None,
        ppe_text=None,
        type_specific=None,
        created_at=now,
        updated_at=now,
        tenant_id="tenant-1",
        completion_text=None,
    )


def _make_member(person_id: str, role: str) -> SimpleNamespace:
    """Фиктивный WorkPermitMember."""
    return SimpleNamespace(
        id=uuid.uuid4(),
        person_id=uuid.UUID(person_id),
        role=role,
        created_at=datetime(2026, 6, 23, 10, 0, 0, tzinfo=timezone.utc),
        work_permit_id=uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        tenant_id="tenant-1",
    )


def _make_tenant() -> SimpleNamespace:
    return SimpleNamespace(id="tenant-1")


def _make_person_row(pid: str, qualifications: list) -> tuple:
    """Строка (id, qualifications) для мока session.execute → .all()."""
    return (uuid.UUID(pid), qualifications)


# ---------------------------------------------------------------------------
# Test: электро-наряд с нормальным форманом (group IV) — readiness OK
# ---------------------------------------------------------------------------

PERSON_ID_OK = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


@pytest.mark.asyncio
async def test_electrical_permit_member_group_and_readiness_ok() -> None:
    """Электро-наряд: форман с группой IV → electrical_group=="IV", readiness.ok==True."""
    from app.api.routes.work_permits import _permit_read

    wp = _make_wp(work_type="electrical")
    tenant = _make_tenant()
    member = _make_member(PERSON_ID_OK, "foreman")
    quals = [{"kind": "electrical_safety_group", "level": "IV", "name": "Группа IV"}]

    # Мок-результат session.execute для Person-запроса
    person_result = MagicMock()
    person_result.all.return_value = [_make_person_row(PERSON_ID_OK, quals)]

    session = AsyncMock()
    session.execute.return_value = person_result

    with patch(
        "app.api.routes.work_permits.list_members",
        new=AsyncMock(return_value=[member]),
    ):
        result = await _permit_read(session, tenant, wp)

    assert isinstance(result, WorkPermitRead)
    assert len(result.members) == 1
    m = result.members[0]
    assert m.electrical_group == "IV", f"ожидали 'IV', получили {m.electrical_group!r}"
    assert result.electrical_group_readiness is not None
    assert result.electrical_group_readiness.ok is True
    assert result.electrical_group_readiness.insufficient == []


# ---------------------------------------------------------------------------
# Test: электро-наряд с форманом группы II → readiness NOT ok
# ---------------------------------------------------------------------------

PERSON_ID_BAD = "cccccccc-cccc-cccc-cccc-cccccccccccc"


@pytest.mark.asyncio
async def test_electrical_permit_foreman_group_ii_readiness_fail() -> None:
    """Форман с группой II — ниже минимума III → readiness.ok==False."""
    from app.api.routes.work_permits import _permit_read

    wp = _make_wp(work_type="electrical")
    tenant = _make_tenant()
    member = _make_member(PERSON_ID_BAD, "foreman")
    quals = [{"kind": "electrical_safety_group", "level": "II", "name": "Группа II"}]

    person_result = MagicMock()
    person_result.all.return_value = [_make_person_row(PERSON_ID_BAD, quals)]

    session = AsyncMock()
    session.execute.return_value = person_result

    with patch(
        "app.api.routes.work_permits.list_members",
        new=AsyncMock(return_value=[member]),
    ):
        result = await _permit_read(session, tenant, wp)

    assert result.electrical_group_readiness is not None
    assert result.electrical_group_readiness.ok is False
    insufficient = result.electrical_group_readiness.insufficient
    assert len(insufficient) == 1
    item = insufficient[0]
    assert str(item["person_id"]) == PERSON_ID_BAD
    assert item["role"] == "foreman"
    assert item["group"] == "II"
    assert item["required"] == "III"

    # Сам член должен показывать electrical_group
    assert result.members[0].electrical_group == "II"


# ---------------------------------------------------------------------------
# Test: не-электро наряд → electrical_group is None, electrical_group_readiness is None
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_non_electrical_permit_no_group_fields() -> None:
    """Не-электро наряд (confined_space) — поля группы отсутствуют (None)."""
    from app.api.routes.work_permits import _permit_read

    wp = _make_wp(work_type="confined_space")
    tenant = _make_tenant()
    member = _make_member(PERSON_ID_OK, "foreman")

    # session.execute не должен вызываться для не-электро
    session = AsyncMock()

    with patch(
        "app.api.routes.work_permits.list_members",
        new=AsyncMock(return_value=[member]),
    ):
        result = await _permit_read(session, tenant, wp)

    # Нет запроса к Person-таблице
    session.execute.assert_not_called()

    assert result.electrical_group_readiness is None
    assert all(m.electrical_group is None for m in result.members)


# ---------------------------------------------------------------------------
# Test: схема QualificationRecord принимает level
# ---------------------------------------------------------------------------

def test_qualification_record_accepts_level() -> None:
    """QualificationRecord.level сохраняется в схеме."""
    from app.schemas.person import QualificationRecord

    q = QualificationRecord(name="Группа по электробезопасности", kind="electrical_safety_group", level="IV")
    assert q.level == "IV"


def test_qualification_record_level_default_none() -> None:
    """QualificationRecord.level по умолчанию None (обратная совместимость)."""
    from app.schemas.person import QualificationRecord

    q = QualificationRecord(name="Допуск по ОТ")
    assert q.level is None


def test_qualification_record_level_survives_sanitize() -> None:
    """_truncate_qualification_row не выкидывает level из словаря."""
    from app.schemas.person import _truncate_qualification_row

    row = {"name": "Группа IV", "kind": "electrical_safety_group", "level": "IV"}
    result = _truncate_qualification_row(row)
    assert result is not None
    assert result.get("level") == "IV"


def test_person_read_qualification_level_roundtrip() -> None:
    """PersonRead корректно обходит level через sanitize-валидатор."""
    from app.schemas.person import PersonRead
    from app.models.models import EmploymentStatus

    data = {
        "id": "11111111-1111-1111-1111-111111111111",
        "company_id": "22222222-2222-2222-2222-222222222222",
        "first_name": "Иван",
        "last_name": "Иванов",
        "employment_status": EmploymentStatus.ACTIVE,
        "qualifications": [
            {"name": "Группа по электробезопасности", "kind": "electrical_safety_group", "level": "IV"}
        ],
        "current_ppe": [],
        "hazardous_factors": [],
    }
    model = PersonRead.model_validate(data)
    assert len(model.qualifications) == 1
    assert model.qualifications[0].level == "IV"


# ---------------------------------------------------------------------------
# Task 3 — готовность по классу напряжения (voltage_level прокидывается в readiness)
# ---------------------------------------------------------------------------

PERSON_ID_FOREMAN_III = "dddddddd-dddd-dddd-dddd-dddddddddddd"


@pytest.mark.asyncio
async def test_electrical_gt_1000_foreman_iii_insufficient() -> None:
    """Электро-наряд gt_1000: форман с группой III < IV → readiness.ok==False, required=='IV'."""
    from app.api.routes.work_permits import _permit_read

    wp = _make_wp(work_type="electrical")
    wp.type_specific = {"voltage_level": "gt_1000"}
    tenant = _make_tenant()
    member = _make_member(PERSON_ID_FOREMAN_III, "foreman")
    quals = [{"kind": "electrical_safety_group", "level": "III", "name": "Группа III"}]

    person_result = MagicMock()
    person_result.all.return_value = [_make_person_row(PERSON_ID_FOREMAN_III, quals)]

    session = AsyncMock()
    session.execute.return_value = person_result

    with patch(
        "app.api.routes.work_permits.list_members",
        new=AsyncMock(return_value=[member]),
    ):
        result = await _permit_read(session, tenant, wp)

    assert result.electrical_group_readiness is not None
    assert result.electrical_group_readiness.ok is False
    insufficient = result.electrical_group_readiness.insufficient
    assert len(insufficient) == 1
    item = insufficient[0]
    assert str(item["person_id"]) == PERSON_ID_FOREMAN_III
    assert item["role"] == "foreman"
    assert item["group"] == "III"
    assert item["required"] == "IV", f"при gt_1000 форман должен иметь IV, получили required={item['required']!r}"


@pytest.mark.asyncio
async def test_electrical_le_1000_foreman_iii_ok() -> None:
    """Электро-наряд le_1000: форман с группой III ≥ III → readiness.ok==True."""
    from app.api.routes.work_permits import _permit_read

    wp = _make_wp(work_type="electrical")
    wp.type_specific = {"voltage_level": "le_1000"}
    tenant = _make_tenant()
    member = _make_member(PERSON_ID_FOREMAN_III, "foreman")
    quals = [{"kind": "electrical_safety_group", "level": "III", "name": "Группа III"}]

    person_result = MagicMock()
    person_result.all.return_value = [_make_person_row(PERSON_ID_FOREMAN_III, quals)]

    session = AsyncMock()
    session.execute.return_value = person_result

    with patch(
        "app.api.routes.work_permits.list_members",
        new=AsyncMock(return_value=[member]),
    ):
        result = await _permit_read(session, tenant, wp)

    assert result.electrical_group_readiness is not None
    assert result.electrical_group_readiness.ok is True
    assert result.electrical_group_readiness.insufficient == []
