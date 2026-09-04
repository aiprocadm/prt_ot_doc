"""Схемы авто-отчёта о состоянии по дисциплинам (Доп. №1 разд. 57.4, срез-50)."""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import Field

from app.schemas.base import BaseSchema


class DisciplineReportRead(BaseSchema):
    """Снимок состояния по дисциплинам арендатора на дату."""

    id: str
    period_start: date
    period_end: date
    #: Сумма проблем по всем дисциплинам на дату (происшествия + просрочки).
    total_issues: int
    #: Человеческий итог: что по дисциплинам, что изменилось, что делать.
    summary: str
    #: Строки по дисциплинам (``overdue_items`` = null — «не считается»),
    #: итоги, динамика к прошлому отчёту, действия.
    payload: dict[str, Any] = Field(default_factory=dict)


class DisciplineReportPage(BaseSchema):
    items: list[DisciplineReportRead]
    total: int


class DisciplineReportRunRead(BaseSchema):
    """Итог «собрать сейчас»: новый отчёт или за эту дату уже был."""

    created: bool
    report: DisciplineReportRead
    #: Сколько уведомлений ушло получателям (срез-51); у повторного запуска 0.
    notified: int = 0
    summary: str
