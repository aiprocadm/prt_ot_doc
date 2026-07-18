from __future__ import annotations

from datetime import date

from app.services.reminders import evaluate_due_date


def test_evaluate_due_date_offset_match() -> None:
    result = evaluate_due_date(
        due_date=date(2026, 3, 20), today=date(2026, 3, 13), offsets_days=[30, 14, 7, 1, 0]
    )
    assert result is not None
    assert result.offset_day == 7
    assert result.is_overdue is False


def test_evaluate_due_date_overdue() -> None:
    result = evaluate_due_date(
        due_date=date(2026, 3, 10), today=date(2026, 3, 13), offsets_days=[7, 1, 0]
    )
    assert result is not None
    assert result.is_overdue is True
