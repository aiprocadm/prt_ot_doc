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
