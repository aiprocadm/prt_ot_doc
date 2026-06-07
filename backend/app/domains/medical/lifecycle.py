"""Medical domain pure logic — FSM, periodicity, contingent, suspension rule.

No DB / no app-service imports (only the enum types from app.models.models).
"""
from __future__ import annotations

import enum
from datetime import date, timedelta

from app.models.models import (
    MedicalExamKind,
    MedicalFitness,
    MedicalReferralStatus,
)

_R = MedicalReferralStatus

ALLOWED_TRANSITIONS: dict[MedicalReferralStatus, frozenset[MedicalReferralStatus]] = {
    _R.ISSUED: frozenset({_R.SCHEDULED, _R.CANCELLED}),
    _R.SCHEDULED: frozenset({_R.COMPLETED, _R.CANCELLED}),
    _R.COMPLETED: frozenset(),
    _R.CANCELLED: frozenset(),
}
TERMINAL_STATES: frozenset[MedicalReferralStatus] = frozenset({_R.COMPLETED, _R.CANCELLED})

# Segregation of duties: only these roles may lift a medical suspension.
LIFT_SUSPENSION_ROLES: frozenset[str] = frozenset({"admin", "owner"})

# Default periodicity (days) by exam kind when no norm provides interval_days.
DEFAULT_INTERVAL_DAYS: dict[MedicalExamKind, int] = {
    MedicalExamKind.PERIODIC: 365,
    MedicalExamKind.PRELIMINARY: 0,
    MedicalExamKind.PSYCHIATRIC: 1825,
    MedicalExamKind.FLUOROGRAPHY: 365,
    MedicalExamKind.HEALTH_BOOK: 365,
}


class InvalidTransition(Exception):
    def __init__(self, current: MedicalReferralStatus, target: MedicalReferralStatus) -> None:
        self.current = current
        self.target = target
        super().__init__(f"Cannot transition referral from {current.value} to {target.value}")


def validate_transition(current: MedicalReferralStatus, target: MedicalReferralStatus) -> None:
    if current == target:
        return
    if target not in ALLOWED_TRANSITIONS[current]:
        raise InvalidTransition(current, target)


def is_terminal(status: MedicalReferralStatus) -> bool:
    return status in TERMINAL_STATES


def is_overdue(due_at: date | None, status: MedicalReferralStatus, today: date) -> bool:
    return due_at is not None and due_at < today and status not in TERMINAL_STATES


def requires_result(target: MedicalReferralStatus) -> bool:
    return target == MedicalReferralStatus.COMPLETED
