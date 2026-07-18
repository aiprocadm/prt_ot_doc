from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class ReminderEvaluation:
    offset_day: int
    is_overdue: bool


def evaluate_due_date(*, due_date: date, today: date, offsets_days: list[int]) -> ReminderEvaluation | None:
    """Evaluate reminder state for a single due date.

    Returns matching offset for a due-soon reminder or overdue marker.
    """

    normalized = sorted({int(value) for value in offsets_days}, reverse=True)
    days_left = (due_date - today).days
    if due_date < today:
        return ReminderEvaluation(offset_day=max(days_left, -9999), is_overdue=True)
    if days_left in normalized:
        return ReminderEvaluation(offset_day=days_left, is_overdue=False)
    return None

