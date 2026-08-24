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
    #: разд. 54.1 «регламентные работы»: последняя ПОДТВЕРЖДЁННАЯ работа —
    #: срок без неё это обещание, а не доказательство. Считается при чтении.
    last_maintenance_on: date | None = None
    last_maintenance_result: str | None = None


class FireEquipmentPage(BaseSchema):
    items: list[FireEquipmentRead]
    total: int


class FireMaintenanceCreate(BaseSchema):
    equipment_id: str = Field(min_length=1, max_length=36)
    kind: str = Field(min_length=1, max_length=32)
    performed_on: date
    result: str = Field(min_length=1, max_length=32)
    performer: str | None = Field(default=None, max_length=255)
    notes: str | None = None
    next_due: date | None = None


class FireMaintenanceRead(BaseSchema):
    id: str
    equipment_id: str
    kind: str
    #: вид и результат словами — перевод делает сервер (прецедент тренировок)
    kind_label: str
    performed_on: date
    result: str
    result_label: str
    performer: str | None = None
    notes: str | None = None
    next_due: date | None = None
    #: перенесла ли эта запись срок у средства; «неисправно» не переносит
    shifted_due: bool = False


class FireMaintenancePage(BaseSchema):
    items: list[FireMaintenanceRead]
    total: int


class FireDrillCreate(BaseSchema):
    kind: str = Field(min_length=1, max_length=32)
    title: str = Field(min_length=1, max_length=255)
    planned_on: date
    site_id: str | None = Field(default=None, min_length=1, max_length=36)
    scenario: str | None = None
    held_on: date | None = None
    participants: int | None = Field(default=None, ge=0, le=100000)
    outcome: str | None = Field(default=None, max_length=32)
    findings: str | None = None


class FireDrillUpdate(BaseSchema):
    kind: str | None = Field(default=None, min_length=1, max_length=32)
    title: str | None = Field(default=None, min_length=1, max_length=255)
    planned_on: date | None = None
    site_id: str | None = Field(default=None, max_length=36)
    scenario: str | None = None
    held_on: date | None = None
    participants: int | None = Field(default=None, ge=0, le=100000)
    outcome: str | None = Field(default=None, max_length=32)
    findings: str | None = None


class FireDrillRead(BaseSchema):
    id: str
    kind: str
    #: вид словами — экран не должен переводить коды сам (прецедент среза-3)
    kind_label: str
    title: str
    planned_on: date
    held_on: date | None = None
    site_id: str | None = None
    scenario: str | None = None
    participants: int | None = None
    outcome: str | None = None
    outcome_label: str | None = None
    findings: str | None = None
    #: planned / held / overdue — считается ПРИ ЧТЕНИИ, полем не хранится
    #: (хранимый статус разъезжается с календарём в первый же день)
    status: str


class FireDrillPage(BaseSchema):
    items: list[FireDrillRead]
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
    #: разд. 54.1 «регламентные работы»: средства, у которых нет НИ ОДНОЙ
    #: записи о выполненной работе — срок стоит, а подтвердить его нечем
    units_without_maintenance: int = 0
    #: разд. 54.1 «Тренировки и учения»: план прошёл, факта нет
    overdue_drills: int = 0
    #: назначенные вперёд — не просрочка, но показывать надо (иначе пустой
    #: план-график и заполненный выглядят на экране одинаково)
    planned_drills: int = 0
    #: дата последней ПРОВЕДЁННОЙ тренировки; None — не проводилась ни разу
    last_drill_on: date | None = None
    #: сколько дней прошло с последней тренировки. ГРАНИЦА: интервал «не реже
    #: раза в полгода» (ППР РФ) сводка НЕ судит — норма обязательна для
    #: объектов с массовым пребыванием людей, а признака массового пребывания
    #: у площадки в данных нет. Отдаём факт, вывод делает специалист.
    days_since_last_drill: int | None = None
