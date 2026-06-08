"""Domain-neutral readiness helpers shared across bounded contexts.

Lifted from ``domains/medical/lifecycle.py`` so non-medical contours (e.g.
contractors) can reuse deadline classification without importing medical.
"""
from __future__ import annotations

import enum
from datetime import date, timedelta


class ContingentItemStatus(str, enum.Enum):
    """Per-requirement deadline state: ok / due_soon / overdue / missing."""

    OK = "ok"
    DUE_SOON = "due_soon"
    OVERDUE = "overdue"
    MISSING = "missing"


def classify(
    latest_valid_until: date | None, today: date, warning_days: int = 30
) -> ContingentItemStatus:
    """Classify a requirement by its latest valid_until date."""
    if latest_valid_until is None:
        return ContingentItemStatus.MISSING
    if latest_valid_until < today:
        return ContingentItemStatus.OVERDUE
    if latest_valid_until <= today + timedelta(days=warning_days):
        return ContingentItemStatus.DUE_SOON
    return ContingentItemStatus.OK
