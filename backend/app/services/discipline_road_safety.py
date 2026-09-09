"""Допущенный водитель и истёкшее удостоверение — одна формула (BIZ-54-57 срез-88).

Удостоверение считается у водителя, допущенного к управлению (``Driver.status
== "admitted"``, не удалён): просроченные права отстранённого или уволенного
ничего не блокируют. Пустая дата — «сведений нет» (бессрочных удостоверений
не бывает), это не просрочка. До среза-88 правило повторяли три места —
цифры дисциплины по людям (``discipline_numbers``), источник
``road_safety_driver`` общего календаря (``calendar_aggregator``) и сводка
внимания по портфелю клиентов (``domains/managed_clients``); теперь условия
живут здесь и подставляются в любой запрос, как у обучения (срез-77).
"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import ColumnElement

from app.models.road_safety import Driver

#: Состояние «допущен к управлению» — одно слово на весь продукт.
ADMITTED = "admitted"

__all__ = ["admitted_driver_where", "expired_license_where", "is_admitted"]


def is_admitted(driver: Any) -> bool:
    """То же правило для УЖЕ ЗАГРУЖЕННОЙ записи (срез-129).

    ``admitted_driver_where`` собирает условия для запроса; когда водитель уже
    в руках, сравнение состояния строкой заводит вторую копию правила — ту же
    ошибку, что чинил срез-88, только в другой форме. Приём общий с
    ``person_scope.is_employed`` (срез-121).
    """

    return (
        getattr(driver, "deleted_at", None) is None and getattr(driver, "status", None) == ADMITTED
    )


def admitted_driver_where(tenant_id: str) -> tuple[ColumnElement[bool], ...]:
    """Условия «допущенный к управлению водитель арендатора»."""

    return (
        Driver.tenant_id == tenant_id,
        Driver.deleted_at.is_(None),
        Driver.status == ADMITTED,
    )


def expired_license_where(tenant_id: str, today: date) -> tuple[ColumnElement[bool], ...]:
    """Условия «удостоверение допущенного водителя истекло к дате»."""

    return (
        *admitted_driver_where(tenant_id),
        Driver.license_due.is_not(None),
        Driver.license_due < today,
    )
