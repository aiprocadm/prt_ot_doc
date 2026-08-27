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


class ProfileCreate(BaseSchema):
    site_id: str = Field(min_length=1, max_length=36)
    category: str = Field(min_length=1, max_length=16)
    decision_number: str | None = Field(default=None, max_length=128)
    decision_date: date | None = None
    responsible: str | None = Field(default=None, max_length=255)
    notes: str | None = None


class ProfileUpdate(BaseSchema):
    category: str | None = Field(default=None, min_length=1, max_length=16)
    decision_number: str | None = Field(default=None, max_length=128)
    decision_date: date | None = None
    responsible: str | None = Field(default=None, max_length=255)
    notes: str | None = None


class ProfileRead(BaseSchema):
    """Сведения по ГО об объекте.

    ГРАНИЦА: полей «предлагаемая категория», «требуемые планы» и
    «соответствует ли объект» здесь НЕТ — категорирование выполняет орган.
    """

    id: str
    site_id: str
    site_name: str | None = None
    category: str
    category_label: str
    decision_number: str | None = None
    decision_date: date | None = None
    responsible: str | None = None
    notes: str | None = None


class ProfilePage(BaseSchema):
    items: list[ProfileRead]
    total: int


class CdDocumentCreate(BaseSchema):
    kind: str = Field(min_length=1, max_length=32)
    title: str = Field(min_length=1, max_length=255)
    number: str | None = Field(default=None, max_length=64)
    site_id: str | None = Field(default=None, max_length=36)
    approved_on: date | None = None
    review_due: date | None = None
    responsible: str | None = Field(default=None, max_length=255)
    notes: str | None = None


class CdDocumentUpdate(BaseSchema):
    kind: str | None = Field(default=None, min_length=1, max_length=32)
    title: str | None = Field(default=None, min_length=1, max_length=255)
    number: str | None = Field(default=None, max_length=64)
    site_id: str | None = Field(default=None, max_length=36)
    approved_on: date | None = None
    review_due: date | None = None
    responsible: str | None = Field(default=None, max_length=255)
    notes: str | None = None


class CdDocumentRead(BaseSchema):
    id: str
    kind: str
    kind_label: str
    title: str
    number: str | None = None
    site_id: str | None = None
    approved_on: date | None = None
    review_due: date | None = None
    responsible: str | None = None
    notes: str | None = None
    #: ok / due_soon / overdue — считается ПРИ ЧТЕНИИ;
    #: пустой срок означает БЕССРОЧНО, а не «просрочено»
    review_status: str
    review_status_label: str


class CdDocumentPage(BaseSchema):
    items: list[CdDocumentRead]
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
    #: разд. 56.1 «категорирование и планирование»
    profiles_total: int = 0
    #: категория → число объектов; ключи всегда все четыре, чтобы «ноль
    #: объектов первой категории» отличался от «поле не пришло»
    profiles_by_category: dict[str, int] = Field(default_factory=dict)
    planning_documents: int = 0
    #: документы с прошедшим сроком пересмотра (по ВНЕСЁННОМУ сроку)
    planning_review_overdue: int = 0
