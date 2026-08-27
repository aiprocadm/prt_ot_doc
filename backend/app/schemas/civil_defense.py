"""Схемы контура ГО и ЧС (Доп. №1 разд. 56.1)."""

from __future__ import annotations

from datetime import date

from pydantic import Field

from app.schemas.base import BaseSchema


class FormationCreate(BaseSchema):
    name: str = Field(min_length=1, max_length=255)
    kind: str = Field(min_length=1, max_length=16)
    purpose: str | None = Field(default=None, max_length=255)
    commander_person_id: str | None = Field(default=None, max_length=36)
    equipment_notes: str | None = None
    notes: str | None = None


class FormationUpdate(BaseSchema):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    kind: str | None = Field(default=None, min_length=1, max_length=16)
    purpose: str | None = Field(default=None, max_length=255)
    commander_person_id: str | None = Field(default=None, max_length=36)
    equipment_notes: str | None = None
    notes: str | None = None


class FormationRead(BaseSchema):
    """Формирование вместе с ФИО командира и действующей численностью.

    ГРАНИЦА: полей «требуется формирований» и «недоукомплектовано» здесь НЕТ —
    обязанность создавать формирования и их штат определяют категория
    организации по ГО и орган управления ГОЧС.
    """

    id: str
    name: str
    kind: str
    kind_label: str
    purpose: str | None = None
    commander_person_id: str | None = None
    #: ФИО из ядра; None — командир не назначен
    commander_name: str | None = None
    equipment_notes: str | None = None
    notes: str | None = None
    #: действующие члены состава (без выведенных)
    members_active: int = 0


class FormationPage(BaseSchema):
    items: list[FormationRead]
    total: int


class FormationMemberCreate(BaseSchema):
    person_id: str = Field(min_length=1, max_length=36)
    role_in_formation: str | None = Field(default=None, max_length=128)
    assigned_on: date | None = None
    notes: str | None = None


class FormationMemberUpdate(BaseSchema):
    role_in_formation: str | None = Field(default=None, max_length=128)
    assigned_on: date | None = None
    #: дата вывода из состава; null в PATCH снимает вывод
    released_on: date | None = None
    notes: str | None = None


class FormationMemberRead(BaseSchema):
    id: str
    formation_id: str
    person_id: str
    #: ФИО из ядра — состав не заводит своих «бойцов»
    person_name: str
    role_in_formation: str | None = None
    assigned_on: date | None = None
    released_on: date | None = None
    notes: str | None = None
    #: active / released — считается ПРИ ЧТЕНИИ по дате вывода
    status: str
    status_label: str


class FormationMemberPage(BaseSchema):
    items: list[FormationMemberRead]
    total: int


class CivilDefenseReadinessRead(BaseSchema):
    """Сводка ГО и ЧС: формирования и их составы.

    Считаются ФАКТЫ о внесённом. «Без командира» — факт, а не нарушение:
    платформа не знает штатных требований к конкретному формированию.
    """

    total_formations: int
    #: вид → число; ключи всегда оба, чтобы «ноль НФГО» отличался от
    #: «поле не пришло»
    by_kind: dict[str, int]
    without_commander: int
    #: действующие члены всех составов (выведенные не считаются)
    members_active: int
