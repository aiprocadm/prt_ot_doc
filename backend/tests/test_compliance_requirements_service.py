"""Срез-147: правила реестра требований считаются и без явной даты.

До среза параметр ``today`` затенял функцию ``today()``: вызов без даты падал
с ``TypeError`` — ручки всегда передавали дату, поэтому дефект не всплывал.
"""

from __future__ import annotations

from datetime import date, timedelta

from app.domains.npa.requirements import days_left, display_name, is_overdue, today
from app.models.compliance_requirements import ComplianceRequirement
from app.models.identity import User


def _row(**fields) -> ComplianceRequirement:
    fields.setdefault("status", "active")
    return ComplianceRequirement(code="ОТ-1", title="Проверка", **fields)


def test_просрочка_и_остаток_дней_считаются_от_сегодня_по_умолчанию() -> None:
    yesterday = today() - timedelta(days=1)
    tomorrow = today() + timedelta(days=1)
    assert is_overdue(_row(next_due_at=yesterday)) is True
    assert is_overdue(_row(next_due_at=tomorrow)) is False
    assert is_overdue(_row(next_due_at=yesterday, status="retired")) is False
    assert is_overdue(_row(next_due_at=None)) is False
    assert days_left(_row(next_due_at=tomorrow)) == 1
    assert days_left(_row(next_due_at=yesterday)) == -1
    assert days_left(_row(next_due_at=None)) is None
    # Явная дата по-прежнему главнее часов.
    assert is_overdue(_row(next_due_at=date(2020, 1, 1)), date(2019, 12, 31)) is False


def test_имя_на_витрине_без_имени_почта() -> None:
    assert display_name(User(email="a@example.com", full_name="Иванова Мария")) == "Иванова Мария"
    assert display_name(User(email="a@example.com", full_name="   ")) == "a@example.com"
