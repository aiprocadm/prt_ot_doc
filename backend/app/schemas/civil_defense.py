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


class DrillCreate(BaseSchema):
    kind: str = Field(min_length=1, max_length=32)
    title: str = Field(min_length=1, max_length=255)
    #: учение рождается ЗАПЛАНИРОВАННЫМ — иначе плана-графика нет
    planned_on: date
    formation_id: str | None = Field(default=None, max_length=36)
    site_id: str | None = Field(default=None, max_length=36)
    scenario: str | None = None
    participants: int | None = Field(default=None, ge=0)
    notes: str | None = None


class DrillUpdate(BaseSchema):
    kind: str | None = Field(default=None, min_length=1, max_length=32)
    title: str | None = Field(default=None, min_length=1, max_length=255)
    planned_on: date | None = None
    held_on: date | None = None
    formation_id: str | None = Field(default=None, max_length=36)
    site_id: str | None = Field(default=None, max_length=36)
    scenario: str | None = None
    participants: int | None = Field(default=None, ge=0)
    outcome: str | None = Field(default=None, max_length=32)
    findings: str | None = None


class DrillRead(BaseSchema):
    """Учение вместе с состоянием и названием задействованного формирования.

    ГРАНИЦА: полей «требуемая периодичность» и «следующее учение» здесь НЕТ —
    периодичность установлена постановлением и категорией организации по ГО.
    """

    id: str
    kind: str
    kind_label: str
    title: str
    planned_on: date
    held_on: date | None = None
    formation_id: str | None = None
    #: название формирования; None — учение общеобъектовое
    formation_name: str | None = None
    site_id: str | None = None
    scenario: str | None = None
    participants: int | None = None
    outcome: str | None = None
    outcome_label: str | None = None
    findings: str | None = None
    #: planned / held / overdue — считается ПРИ ЧТЕНИИ по датам
    status: str
    status_label: str


class DrillPage(BaseSchema):
    items: list[DrillRead]
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
    #: разд. 56.1 «учения и тренировки»: план-график и журнал проведённых
    drills_total: int = 0
    #: назначенные, срок которых прошёл, а протокола нет
    drills_overdue: int = 0
    drills_held_this_year: int = 0
