"""Схемы контура ПБ (Доп. №1 разд. 54.1): первичные средства и системы защиты."""

from __future__ import annotations

from datetime import date

from pydantic import Field

from app.schemas.base import BaseSchema


class FireEquipmentCreate(BaseSchema):
    kind: str = Field(min_length=1, max_length=32)
    label: str = Field(min_length=1, max_length=255)
    site_id: str | None = Field(default=None, min_length=1, max_length=36)
    location: str | None = Field(default=None, max_length=255)
    recharge_due: date | None = None
    inspection_due: date | None = None
    status: str = Field(default="active", max_length=32)


class FireEquipmentUpdate(BaseSchema):
    kind: str | None = Field(default=None, min_length=1, max_length=32)
    label: str | None = Field(default=None, min_length=1, max_length=255)
    site_id: str | None = Field(default=None, max_length=36)
    location: str | None = Field(default=None, max_length=255)
    recharge_due: date | None = None
    inspection_due: date | None = None
    status: str | None = Field(default=None, max_length=32)


class FireEquipmentRead(BaseSchema):
    id: str
    kind: str
    label: str
    site_id: str | None = None
    location: str | None = None
    recharge_due: date | None = None
    inspection_due: date | None = None
    status: str


class FireEquipmentPage(BaseSchema):
    items: list[FireEquipmentRead]
    total: int


class FireReadinessRead(BaseSchema):
    """Готовность к проверке МЧС: сроки, которые уже горят или скоро сгорят."""

    total_units: int
    overdue_recharge: int
    overdue_inspection: int
    due_soon: int
    #: горизонт «скоро» в днях — чтобы цифра на экране не требовала пояснений
    due_soon_days: int
    #: разд. 54.1 «контроль сроков»: просроченные ПРОТИВОПОЖАРНЫЕ инструктажи
    #: (виды fire_* и ПТМ) — вторая половина готовности к проверке МЧС
    overdue_fire_briefings: int
