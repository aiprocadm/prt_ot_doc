"""Declarative dataset registry for the report builder (P10-07 §24.3).

Каждый датасет = плоский список типизированных колонок + билдер базового
SELECT. Engine оборачивает базовый select в subquery и применяет фильтры /
группировку / сортировку единообразно по labeled-колонкам — поэтому
вычислимые колонки (is_overdue, on_hand, below_min) ОБЯЗАНЫ быть
SQL-выражениями, а не Python-постобработкой. Ключи labeled-колонок билдера
байт-в-байт совпадают со списком ``columns`` (пинуется тестом реестра).

Enum-контракт. Enum-колонки намеренно сохраняют ORM Enum-тип; engine ОБЯЗАН
фильтровать по типизированной колонке (никогда не cast к тексту) и рендерить
через ``member.value``. ``enum_values`` в ``ColumnSpec`` — это .value-токены
для UI/валидации, а физическое хранение может быть NAME-based (plain
``sa.Enum``: Training.status, Incident.incident_type/status/severity хранят
'REPORTED', 'COMPLETED', ...) или value-based (``native_enum``:
PPEItem.category хранит 'head', ...). Bind processor типизированной колонки
нормализует оба случая при фильтрации; cast к тексту или рендер без
``.value`` дадут тихо неверные результаты.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from sqlalchemy import Select, case, func, select

from app.models.models import (
    Company,
    Incident,
    IncidentSeverity,
    IncidentStatus,
    IncidentType,
    Person,
    PPEItem,
    PPEItemCategory,
    PPEStockBatch,
    Site,
    Training,
    TrainingStatus,
)
from app.models.risk import Risk  # не ре-экспортирован в app.models.models

OPS_BY_KIND: dict[str, tuple[str, ...]] = {
    "string": ("eq", "neq", "contains"),
    "number": ("eq", "gte", "lte"),
    "date": ("eq", "gte", "lte"),
    "datetime": ("eq", "gte", "lte"),
    "enum": ("eq", "in"),
    "bool": ("eq",),
}


@dataclass(frozen=True)
class ColumnSpec:
    key: str
    label: str
    kind: str  # ключ OPS_BY_KIND
    aggregatable: bool = False
    enum_cls: type[enum.Enum] | None = None

    @property
    def ops(self) -> tuple[str, ...]:
        return OPS_BY_KIND[self.kind]

    @property
    def enum_values(self) -> list[str] | None:
        if self.enum_cls is None:
            return None
        return [m.value for m in self.enum_cls]


@dataclass(frozen=True)
class DatasetSpec:
    code: str
    title: str
    columns: tuple[ColumnSpec, ...]
    build_stmt: Callable[[str, datetime], Select]

    def column(self, key: str) -> ColumnSpec | None:
        for col in self.columns:
            if col.key == key:
                return col
        return None


def _employees_training_stmt(tenant_id: str, now: datetime) -> Select:
    return (
        select(
            (Person.last_name + " " + Person.first_name).label("person_name"),
            Person.position_title.label("position_title"),
            Training.course_name.label("course_name"),
            Training.status.label("status"),
            Training.scheduled_at.label("scheduled_at"),
            Training.completed_at.label("completed_at"),
            Training.expires_at.label("expires_at"),
            case(
                ((Training.expires_at.is_not(None)) & (Training.expires_at < now), True),
                else_=False,
            ).label("is_overdue"),
        )
        .select_from(Training)
        .join(Person, Person.id == Training.person_id)
        .where(Training.tenant_id == tenant_id, Person.deleted_at.is_(None))
    )


def _incidents_stmt(tenant_id: str, now: datetime) -> Select:
    _ = now
    return (
        select(
            Incident.title.label("title"),
            Incident.incident_type.label("incident_type"),
            Incident.status.label("status"),
            Incident.severity.label("severity"),
            Incident.occurred_at.label("occurred_at"),
            Company.name.label("company_name"),
            Site.name.label("site_name"),
        )
        .select_from(Incident)
        .join(Company, Company.id == Incident.company_id)
        .join(Site, Site.id == Incident.site_id)
        .where(Incident.tenant_id == tenant_id, Incident.deleted_at.is_(None))
    )


def _risks_stmt(tenant_id: str, now: datetime) -> Select:
    _ = now
    return (
        select(
            Risk.hazard.label("hazard"),
            Risk.probability.label("probability"),
            Risk.severity.label("severity"),
            Risk.level.label("level"),
            Risk.controls.label("controls"),
            Company.name.label("company_name"),
            Site.name.label("site_name"),
        )
        .select_from(Risk)
        .join(Company, Company.id == Risk.company_id)
        .outerjoin(Site, Site.id == Risk.site_id)
        .where(Risk.tenant_id == tenant_id)
    )


def _ppe_warehouse_stmt(tenant_id: str, now: datetime) -> Select:
    _ = now
    on_hand_sq = (
        select(
            PPEStockBatch.item_id.label("item_id"),
            func.coalesce(func.sum(PPEStockBatch.quantity), 0).label("on_hand"),
        )
        .where(PPEStockBatch.tenant_id == tenant_id, PPEStockBatch.deleted_at.is_(None))
        .group_by(PPEStockBatch.item_id)
        .subquery()
    )
    on_hand = func.coalesce(on_hand_sq.c.on_hand, 0)
    return (
        select(
            PPEItem.name.label("item_name"),
            PPEItem.code.label("code"),
            PPEItem.category.label("category"),
            PPEItem.min_stock.label("min_stock"),
            on_hand.label("on_hand"),
            case((on_hand < PPEItem.min_stock, True), else_=False).label("below_min"),
        )
        .select_from(PPEItem)
        .outerjoin(on_hand_sq, on_hand_sq.c.item_id == PPEItem.id)
        .where(PPEItem.tenant_id == tenant_id, PPEItem.deleted_at.is_(None))
    )


DATASETS: dict[str, DatasetSpec] = {
    "employees_training": DatasetSpec(
        code="employees_training",
        title="Обучение сотрудников",
        columns=(
            ColumnSpec("person_name", "Сотрудник", "string"),
            ColumnSpec("position_title", "Должность", "string"),
            ColumnSpec("course_name", "Курс", "string"),
            ColumnSpec("status", "Статус", "enum", enum_cls=TrainingStatus),
            ColumnSpec("scheduled_at", "Запланировано", "datetime"),
            ColumnSpec("completed_at", "Пройдено", "datetime"),
            ColumnSpec("expires_at", "Действует до", "datetime"),
            ColumnSpec("is_overdue", "Просрочено", "bool"),
        ),
        build_stmt=_employees_training_stmt,
    ),
    "incidents": DatasetSpec(
        code="incidents",
        title="Инциденты",
        columns=(
            ColumnSpec("title", "Название", "string"),
            ColumnSpec("incident_type", "Тип", "enum", enum_cls=IncidentType),
            ColumnSpec("status", "Статус", "enum", enum_cls=IncidentStatus),
            ColumnSpec("severity", "Тяжесть", "enum", enum_cls=IncidentSeverity),
            ColumnSpec("occurred_at", "Дата", "datetime"),
            ColumnSpec("company_name", "Компания", "string"),
            ColumnSpec("site_name", "Объект", "string"),
        ),
        build_stmt=_incidents_stmt,
    ),
    "risks": DatasetSpec(
        code="risks",
        title="Реестр рисков",
        columns=(
            ColumnSpec("hazard", "Опасность", "string"),
            ColumnSpec("probability", "Вероятность", "number", aggregatable=True),
            ColumnSpec("severity", "Тяжесть", "number", aggregatable=True),
            ColumnSpec("level", "Уровень", "number", aggregatable=True),
            ColumnSpec("controls", "Меры контроля", "string"),
            ColumnSpec("company_name", "Компания", "string"),
            ColumnSpec("site_name", "Объект", "string"),
        ),
        build_stmt=_risks_stmt,
    ),
    "ppe_warehouse": DatasetSpec(
        code="ppe_warehouse",
        title="СИЗ: остатки на складе",
        columns=(
            ColumnSpec("item_name", "Позиция", "string"),
            ColumnSpec("code", "Код", "string"),
            ColumnSpec("category", "Категория", "enum", enum_cls=PPEItemCategory),
            ColumnSpec("min_stock", "Мин. остаток", "number", aggregatable=True),
            ColumnSpec("on_hand", "Остаток", "number", aggregatable=True),
            ColumnSpec("below_min", "Ниже минимума", "bool"),
        ),
        build_stmt=_ppe_warehouse_stmt,
    ),
}
