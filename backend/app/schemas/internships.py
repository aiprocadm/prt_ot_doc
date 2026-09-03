"""Схемы стажировки на рабочем месте (ядро; требование Доп. №1 разд. 56.2).

Сущность ядровая, а не БДДшная: комплект документов печатает «Стажировка: N
смен» в первичном инструктаже НОВОГО РАБОТНИКА — по охране труда, любому
рабочему. Контур дисциплины отбирает свои записи через ``discipline``.
"""

from __future__ import annotations

from datetime import date

from pydantic import Field

from app.schemas.base import BaseSchema


class InternshipCreate(BaseSchema):
    """Назначение стажировки.

    Полей «требуется ли стажировка» и «достаточно ли смен» здесь НЕТ: это
    следует из профессии, стажа работника и локального приказа.
    """

    person_id: str = Field(min_length=1, max_length=36)
    #: наставник НЕОБЯЗАТЕЛЕН: в приказе его иногда называют позже, и
    #: требовать сразу значило бы заставлять выдумывать
    mentor_person_id: str | None = Field(default=None, max_length=36)
    #: код дисциплины из общего словаря; пусто — «не размечено», а НЕ «охрана
    #: труда»
    discipline: str | None = Field(default=None, max_length=32)
    #: на что стажировка — свободная строка: профессий и типов техники тысячи
    subject: str | None = Field(default=None, max_length=255)
    planned_shifts: int = Field(default=0, ge=0)
    completed_shifts: int = Field(default=0, ge=0)
    started_on: date | None = None
    finished_on: date | None = None
    status: str = Field(default="planned", min_length=1, max_length=16)
    notes: str | None = None


class InternshipUpdate(BaseSchema):
    """Правка. Стажёра сменить нельзя — это стажировка другого человека."""

    mentor_person_id: str | None = Field(default=None, max_length=36)
    discipline: str | None = Field(default=None, max_length=32)
    subject: str | None = Field(default=None, max_length=255)
    planned_shifts: int | None = Field(default=None, ge=0)
    completed_shifts: int | None = Field(default=None, ge=0)
    started_on: date | None = None
    finished_on: date | None = None
    status: str | None = Field(default=None, min_length=1, max_length=16)
    notes: str | None = None


class InternshipRead(BaseSchema):
    """Стажировка вместе с недобором смен.

    ГРАНИЦА: полей «требуется ли стажировка», «достаточно ли смен» и «допущен
    ли к самостоятельной работе» здесь НЕТ. Недобор — это ФАКТ расхождения
    плана и факта, а не вердикт о законности допуска.
    """

    id: str
    person_id: str
    #: ФИО — из ядрового ``Person``, в записи не хранится
    person_name: str
    mentor_person_id: str | None = None
    #: пусто — наставник не назначен, а НЕ «неизвестен»
    mentor_name: str | None = None
    discipline: str | None = None
    #: дисциплина словами; пусто, если не размечена
    discipline_label: str | None = None
    subject: str | None = None
    planned_shifts: int
    completed_shifts: int
    #: СЧИТАЕТСЯ ПРИ ЧТЕНИИ: сколько смен осталось до плана
    shifts_remaining: int
    #: СЧИТАЕТСЯ ПРИ ЧТЕНИИ: стажировка ЗАВЕРШЕНА, а смен меньше плана —
    #: формально закрытая стажировка, которой по сменам не было. Это ФАКТ
    #: расхождения, а не вердикт о законности допуска
    completed_short: bool
    started_on: date | None = None
    finished_on: date | None = None
    status: str
    status_label: str
    notes: str | None = None


class InternshipPage(BaseSchema):
    items: list[InternshipRead]
    total: int


class InternshipSummary(BaseSchema):
    """Сводка ОБЩЕГО экрана стажировок — по ВСЕМ записям арендатора.

    Считается В БАЗЕ, а не по загруженной странице списка: плитка «всего» по
    первым двумстам строкам врала бы ровно у тех, у кого стажировок много.
    Сводка БДД считает то же, но только СВОИ (по разметке дисциплиной) — здесь
    дисциплина не отбирается, неразмеченные входят.

    ГРАНИЦА: здесь ФАКТЫ о данных, а не вердикты. «Завершена с недобором» —
    расхождение плана и факта; «активная без наставника» — некому подтвердить
    смены. Нужна ли стажировка и законен ли допуск, сводка не решает.
    """

    total: int
    #: по каждому состоянию из закрытого словаря, нули включены
    by_status: dict[str, int]
    #: завершённые, у которых смен меньше плана
    completed_short: int
    #: назначенные или идущие БЕЗ наставника: у завершённых и отменённых
    #: наставника уже не назначат, поэтому они сюда не входят
    active_without_mentor: int
