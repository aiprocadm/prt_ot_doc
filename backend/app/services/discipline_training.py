"""Просроченные назначения обучения — одна формула на календарь, сводки и блокеры.

Назначение обучения (``TrainingEnrollment``, контур «обучение-next») имеет срок
``due_at``: к этой дате работник должен пройти программу. «Просрочено» —
назначение ещё живое (``assigned`` / ``in_progress``, не удалено), а срок
прошёл. До среза-77 эту формулу считали пять мест по отдельности — цифры
дисциплины в карточке сотрудника, площадок и клиентов (``discipline_numbers``),
блокер готовности и рабочий стол роли (``routes/workspace``), календарь и
внимание сервисного центра (``domains/managed_clients``) — а общий календарь
и Центр внимания о сроке назначения не знали вовсе: их источник
``training_session`` читает старую модель ``TrainingSession``. Строка
«Обучение» в Центре внимания молчала там, где блокер готовности кричал
«просроченные назначения».

Срез-77: формула живёт здесь и одна; общий календарь получил источник
``training_enrollment`` по ней же. Сторож ``tests/test_training_enrollment_formula.py``
не даёт завести новую копию.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import ColumnElement

from app.models.training import TrainingEnrollment

__all__ = [
    "ACTIVE_ENROLLMENT_STATUSES",
    "overdue_training_enrollment_where",
    "pending_training_enrollment_where",
]

#: Состояния, в которых назначение ещё ждёт прохождения. ``passed`` / ``failed``
#: (``training_next.py``) — итог получен, срок больше не давит.
ACTIVE_ENROLLMENT_STATUSES: tuple[str, ...] = ("assigned", "in_progress")


def pending_training_enrollment_where(tenant_id: str) -> tuple[ColumnElement[bool], ...]:
    """Условия «живое назначение арендатора со сроком» — для окон календаря."""

    return (
        TrainingEnrollment.tenant_id == tenant_id,
        TrainingEnrollment.deleted_at.is_(None),
        TrainingEnrollment.status.in_(list(ACTIVE_ENROLLMENT_STATUSES)),
        TrainingEnrollment.due_at.is_not(None),
    )


def overdue_training_enrollment_where(
    tenant_id: str, now: datetime
) -> tuple[ColumnElement[bool], ...]:
    """Условия «просроченное назначение арендатора» — подставляются в любой запрос."""

    return (
        *pending_training_enrollment_where(tenant_id),
        TrainingEnrollment.due_at < now,
    )
