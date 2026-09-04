"""Доп. №1 разд. 57.4: авто-отчёт о состоянии по дисциплинам (срез-50).

ТЗ: «авто-отчёты о состоянии по каждой дисциплине (для клиента при аренде /
для заказчика при аутсорсинге)». Заказчика при аутсорсинге закрывает отчёт
авто-аудита клиента (BIZ-51, ``client_audit_report``); здесь — отчёт для
самого арендатора: что у него по каждой дисциплине НА ДАТУ и как это
изменилось с прошлого отчёта.

Отчёт — ЗАПИСЬ, а не пересчёт на лету: разрез «по дисциплинам» на дашборде
и так считает всё нужное, но он про «сейчас». Ценность отчёта в динамике
между неделями, а её пересчёт задним числом не даёт — тот же довод, что у
``ClientAuditReport``.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import JSON, Date, Index, Integer, Text
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TenantBaseModel

__all__ = ["DisciplineStatusReport"]


class DisciplineStatusReport(TenantBaseModel):
    """Снимок состояния по дисциплинам арендатора на дату (разд. 57.4)."""

    __tablename__ = "discipline_status_report"
    __table_args__ = (
        # Отчёты читаются свежие сверху; тем же индексом ищется «отчёт за эту
        # дату уже есть» при дедупликации тика и «предыдущий» для динамики.
        Index("ix_discipline_status_report_feed", "tenant_id", "period_end"),
    )

    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    #: Сумма проблем по всем дисциплинам на дату — для тренда без разбора JSON.
    total_issues: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: Человеческий итог: что по дисциплинам, что изменилось, что делать.
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    #: Структура отчёта (строки по дисциплинам, итоги, динамика, действия).
    payload: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )
