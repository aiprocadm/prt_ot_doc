"""Текстовый отбор по реестрам БДД (Доп. №1 разд. 56.2, срез-123).

Экран БДД грузил по 200 строк каждого реестра и искал В ПАМЯТИ. Пока парк
маленький, разницы нет; у арендатора с большим парком поиск по номеру машины
молча не находит существующую машину — она просто не попала на страницу.
«Ничего не найдено» вместо «вот ваша машина» — худший ответ реестра: человек
верит ему и заводит дубль.

## Решения

**1. Ищем в базе, теми же словами, что на экране.** В подсказке поиска
написано «Поиск по номеру, марке, виду» — значит, вид (закрытый словарь)
обязан находиться по своей ПОДПИСИ: пользователь ищет «грузовой», а в базе
лежит ``truck``. Поэтому запрос сначала переводится в коды словаря, а потом
уже сравнивается с колонкой.

**2. Одно правило на реестр, а не набор частных условий.** Условие собирается
здесь и подставляется в ручку; экран у поиска один, и разные ответы на один и
тот же запрос в разных местах — это не «гибкость», а расхождение.

**3. Пустой запрос — не фильтр.** ``None`` означает «условия нет», а не
«ничего не подходит»: иначе пустая строка поиска очистила бы реестр.
"""

from __future__ import annotations

from collections.abc import Mapping

from sqlalchemy import ColumnElement, String, or_

from app.models.master_data import Person
from app.models.road_safety import (
    ACCIDENT_KINDS,
    DRIVER_STATUSES,
    VEHICLE_KINDS,
    VEHICLE_STATUSES,
    VIOLATION_SOURCES,
    WAYBILL_STATUSES,
    Driver,
    RoadAccident,
    TrafficViolation,
    Vehicle,
    Waybill,
)

__all__ = [
    "accident_search",
    "codes_by_title",
    "driver_search",
    "normalize_needle",
    "vehicle_search",
    "violation_search",
    "waybill_search",
]

#: Длиннее человек в поиск не пишет; ограничение бережёт и индекс, и журнал.
MAX_QUERY_LEN = 200


def normalize_needle(q: str | None) -> str:
    return (q or "").strip()[:MAX_QUERY_LEN]


def codes_by_title(titles: Mapping[str, str], needle: str) -> list[str]:
    """Коды словаря, чья подпись содержит запрос.

    Человек ищет словом, которое видит («грузовой»), а в колонке лежит код
    (``truck``). Без этого перевода поиск по виду и статусу не работал бы
    вовсе, хотя подсказка обещает его.
    """

    lowered = needle.lower()
    return [code for code, title in titles.items() if lowered in title.lower()]


def _person_name_match(pattern: str) -> ColumnElement[bool]:
    return or_(
        Person.last_name.ilike(pattern),
        Person.first_name.ilike(pattern),
        Person.middle_name.ilike(pattern),
    )


def vehicle_search(needle: str) -> ColumnElement[bool] | None:
    """«Поиск по номеру, марке, виду» — ровно то, что обещает подсказка."""

    if not needle:
        return None
    pattern = f"%{needle}%"
    conditions: list[ColumnElement[bool]] = [
        Vehicle.plate_number.ilike(pattern),
        Vehicle.brand_model.ilike(pattern),
        Vehicle.vin.ilike(pattern),
    ]
    kinds = codes_by_title(VEHICLE_KINDS, needle)
    if kinds:
        conditions.append(Vehicle.kind.in_(kinds))
    statuses = codes_by_title(VEHICLE_STATUSES, needle)
    if statuses:
        conditions.append(Vehicle.status.in_(statuses))
    return or_(*conditions)


def driver_search(needle: str) -> ColumnElement[bool] | None:
    """«Поиск по фамилии, удостоверению, категории».

    Требует join с ``Person``: имя водителя живёт в кадровой записи, своей
    копии у водителя нет — и заводить её ради поиска нельзя.
    """

    if not needle:
        return None
    pattern = f"%{needle}%"
    conditions: list[ColumnElement[bool]] = [
        Driver.license_number.ilike(pattern),
        _person_name_match(pattern),
        # Категории — список строк в JSON. Сравниваем как с текстом:
        # «содержит B» находит и ["B"], и ["B","C"]. Разбирать JSON запросом
        # на SQLite и PostgreSQL одинаково нельзя, а поиск обязан работать в
        # обеих (тесты идут на SQLite, бой — на PostgreSQL).
        Driver.categories.cast(String).ilike(pattern),
    ]
    statuses = codes_by_title(DRIVER_STATUSES, needle)
    if statuses:
        conditions.append(Driver.status.in_(statuses))
    return or_(*conditions)


def waybill_search(needle: str) -> ColumnElement[bool] | None:
    """«Поиск по номеру, машине, водителю» — join с машиной и кадровой записью."""

    if not needle:
        return None
    pattern = f"%{needle}%"
    conditions: list[ColumnElement[bool]] = [
        Waybill.number.ilike(pattern),
        Vehicle.plate_number.ilike(pattern),
        Vehicle.brand_model.ilike(pattern),
        _person_name_match(pattern),
    ]
    statuses = codes_by_title(WAYBILL_STATUSES, needle)
    if statuses:
        conditions.append(Waybill.status.in_(statuses))
    return or_(*conditions)


def accident_search(needle: str) -> ColumnElement[bool] | None:
    """«Поиск по месту, машине, водителю, виду»."""

    if not needle:
        return None
    pattern = f"%{needle}%"
    conditions: list[ColumnElement[bool]] = [
        RoadAccident.place.ilike(pattern),
        RoadAccident.gibdd_reference.ilike(pattern),
        Vehicle.plate_number.ilike(pattern),
        _person_name_match(pattern),
    ]
    kinds = codes_by_title(ACCIDENT_KINDS, needle)
    if kinds:
        conditions.append(RoadAccident.kind.in_(kinds))
    return or_(*conditions)


def violation_search(needle: str) -> ColumnElement[bool] | None:
    """«Поиск по машине, водителю, статье»."""

    if not needle:
        return None
    pattern = f"%{needle}%"
    conditions: list[ColumnElement[bool]] = [
        TrafficViolation.article.ilike(pattern),
        Vehicle.plate_number.ilike(pattern),
        _person_name_match(pattern),
    ]
    sources = codes_by_title(VIOLATION_SOURCES, needle)
    if sources:
        conditions.append(TrafficViolation.source.in_(sources))
    return or_(*conditions)
