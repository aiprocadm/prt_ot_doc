"""Medical domain pure logic — FSM, periodicity, contingent, suspension rule.

No DB / no app-service imports (only the enum types from app.models.models).
"""
from __future__ import annotations

import enum
from collections.abc import Iterable
from datetime import date, timedelta
from typing import Tuple

from app.models.models import (
    MedicalExamKind,
    MedicalFitness,
    MedicalReferralStatus,
    MedicalSuspensionReason,
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


# ---------------------------------------------------------------------------
# 2.2 — Periodicity helpers
# ---------------------------------------------------------------------------


def interval_for_kind(kind: MedicalExamKind, norm_interval_days: int | None) -> int:
    if norm_interval_days is not None:
        return norm_interval_days
    return DEFAULT_INTERVAL_DAYS.get(kind, 365)


def compute_valid_until(exam_date: date, interval_days: int) -> date:
    return exam_date + timedelta(days=interval_days)


def next_due(last_exam_date: date | None, interval_days: int, today: date) -> date:
    if last_exam_date is None:
        return today
    return last_exam_date + timedelta(days=interval_days)


# ---------------------------------------------------------------------------
# 2.3 — Contingent classification
# ---------------------------------------------------------------------------


class ContingentItemStatus(str, enum.Enum):
    OK = "ok"
    DUE_SOON = "due_soon"
    OVERDUE = "overdue"
    MISSING = "missing"


def classify(
    latest_valid_until: date | None, today: date, warning_days: int = 30
) -> ContingentItemStatus:
    if latest_valid_until is None:
        return ContingentItemStatus.MISSING
    if latest_valid_until < today:
        return ContingentItemStatus.OVERDUE
    if latest_valid_until <= today + timedelta(days=warning_days):
        return ContingentItemStatus.DUE_SOON
    return ContingentItemStatus.OK


# ---------------------------------------------------------------------------
# 2.4 — Required-kinds resolution (СОУТ influence)
# ---------------------------------------------------------------------------

# norm tuple shape: (position_id, hazard_id|None, working_conditions_class|None, exam_kind)
NormTuple = Tuple[str, str | None, str | None, MedicalExamKind]


def resolve_required_kinds(
    position_id: str,
    working_conditions_class: str | None,
    hazard_ids: set[str],
    norms: Iterable[NormTuple],
) -> set[MedicalExamKind]:
    required: set[MedicalExamKind] = set()
    for n_pos, n_hazard, n_wcc, n_kind in norms:
        if n_pos != position_id:
            continue
        hazard_ok = n_hazard is None or n_hazard in hazard_ids
        wcc_ok = n_wcc is None or n_wcc == working_conditions_class
        if hazard_ok and wcc_ok:
            required.add(n_kind)
    return required


# ---------------------------------------------------------------------------
# 2.5 — Suspension rule
# ---------------------------------------------------------------------------


class SuspensionAction(str, enum.Enum):
    OPEN = "open"
    LIFT = "lift"
    NONE = "none"


def requires_suspension(fitness: MedicalFitness) -> bool:
    return fitness == MedicalFitness.UNFIT


def suspension_action(
    has_active_suspension: bool, new_fitness: MedicalFitness
) -> SuspensionAction:
    if not has_active_suspension and new_fitness == MedicalFitness.UNFIT:
        return SuspensionAction.OPEN
    if has_active_suspension and new_fitness in (
        MedicalFitness.FIT,
        MedicalFitness.FIT_WITH_RESTRICTIONS,
    ):
        return SuspensionAction.LIFT
    return SuspensionAction.NONE


def reason_for(contraindications: list[str]) -> MedicalSuspensionReason:
    return (
        MedicalSuspensionReason.CONTRAINDICATION
        if contraindications
        else MedicalSuspensionReason.UNFIT
    )
