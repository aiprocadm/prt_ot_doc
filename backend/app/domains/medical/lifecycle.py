"""Medical domain pure logic — FSM, periodicity, contingent, suspension rule.

No DB / no app-service imports (only the enum types from app.models.models).
"""
from __future__ import annotations

import enum
from collections.abc import Iterable
from datetime import date, timedelta

from app.domains.shared import ContingentItemStatus, classify  # re-export (back-compat)

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
    """Raised when a referral status transition is not permitted by the FSM."""

    def __init__(self, current: MedicalReferralStatus, target: MedicalReferralStatus) -> None:
        self.current = current
        self.target = target
        super().__init__(f"Cannot transition referral from {current.value} to {target.value}")


def validate_transition(current: MedicalReferralStatus, target: MedicalReferralStatus) -> None:
    """Raise InvalidTransition unless target is reachable from current; self-transition is a no-op."""
    if current == target:
        return
    if target not in ALLOWED_TRANSITIONS[current]:
        raise InvalidTransition(current, target)


def is_terminal(status: MedicalReferralStatus) -> bool:
    """True if the referral status is a terminal state (COMPLETED/CANCELLED)."""
    return status in TERMINAL_STATES


def is_overdue(due_at: date | None, status: MedicalReferralStatus, today: date) -> bool:
    """True when a non-terminal referral is past its due date. today is injected for determinism."""
    return due_at is not None and due_at < today and status not in TERMINAL_STATES


def requires_result(target: MedicalReferralStatus) -> bool:
    """A referral may move to COMPLETED only with a linked result exam."""
    return target == MedicalReferralStatus.COMPLETED


# ---------------------------------------------------------------------------
# 2.2 — Periodicity helpers
# ---------------------------------------------------------------------------


def interval_for_kind(kind: MedicalExamKind, norm_interval_days: int | None) -> int:
    """Periodicity in days: the norm's interval if given, else the per-kind default (fallback 365)."""
    if norm_interval_days is not None:
        return norm_interval_days
    return DEFAULT_INTERVAL_DAYS.get(kind, 365)


def compute_valid_until(exam_date: date, interval_days: int) -> date:
    """valid_until = exam_date + interval_days."""
    return exam_date + timedelta(days=interval_days)


def next_due(last_exam_date: date | None, interval_days: int, today: date) -> date:
    """When the next exam is due: today if never examined, else last_exam_date + interval_days."""
    if last_exam_date is None:
        return today
    return last_exam_date + timedelta(days=interval_days)


# ---------------------------------------------------------------------------
# 2.3 — Contingent classification  (ContingentItemStatus, classify — see shared.py)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# 2.4 — Required-kinds resolution (СОУТ influence)
# ---------------------------------------------------------------------------

# norm tuple shape: (position_id, hazard_id | None, working_conditions_class | None, exam_kind)
NormTuple = tuple[str, str | None, str | None, MedicalExamKind]


def resolve_required_kinds(
    position_id: str,
    working_conditions_class: str | None,
    hazard_ids: set[str],
    norms: Iterable[NormTuple],
) -> set[MedicalExamKind]:
    """Required exam kinds for a position: union of norms matching by position, and
    (hazard in hazard_ids or norm hazard is None) and (working-conditions-class matches or
    norm class is None). This is the СОУТ-influence point."""
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
# 2.6 — §9.2 factor-driven resolution (29н catalog → required kinds)
# ---------------------------------------------------------------------------

# (code, name, exam_kinds, periodicity_months) — ORM-free 29н factor tuple.
FactorTuple = tuple[str, str, tuple["MedicalExamKind", ...], int]

# Worst-first priority of contingent statuses (for per-person rollup).
_STATUS_PRIORITY: dict[str, int] = {"missing": 3, "overdue": 2, "due_soon": 1, "ok": 0}


def factors_for_hazards(
    hazard_factor_codes: set[str], catalog: Iterable[FactorTuple]
) -> set[FactorTuple]:
    """29н factors whose code is mapped by one of the position's hazards."""
    return {f for f in catalog if f[0] in hazard_factor_codes}


def required_exams_from_factors(
    factors: Iterable[FactorTuple],
) -> dict[MedicalExamKind, int]:
    """Union of mandated exam kinds → strictest (min) periodicity in months."""
    result: dict[MedicalExamKind, int] = {}
    for _code, _name, kinds, months in factors:
        for kind in kinds:
            if kind not in result or months < result[kind]:
                result[kind] = months
    return result


def worst_status(statuses: Iterable[str]) -> str:
    """Roll up per-kind contingent statuses to the most severe; 'ok' when empty."""
    worst = "ok"
    for st in statuses:
        if _STATUS_PRIORITY.get(st, 0) > _STATUS_PRIORITY[worst]:
            worst = st
    return worst


# ---------------------------------------------------------------------------
# 2.5 — Suspension rule
# ---------------------------------------------------------------------------


class SuspensionAction(str, enum.Enum):
    """Outcome of evaluating a fitness verdict against an existing suspension: open / lift / none."""

    OPEN = "open"
    LIFT = "lift"
    NONE = "none"


def requires_suspension(fitness: MedicalFitness) -> bool:
    """True when a fitness verdict (UNFIT) mandates a medical suspension."""
    return fitness == MedicalFitness.UNFIT


def suspension_action(
    has_active_suspension: bool, new_fitness: MedicalFitness
) -> SuspensionAction:
    """Decide OPEN (newly unfit), LIFT (now fit/with-restrictions while suspended), or NONE."""
    if not has_active_suspension and new_fitness == MedicalFitness.UNFIT:
        return SuspensionAction.OPEN
    if has_active_suspension and new_fitness in (
        MedicalFitness.FIT,
        MedicalFitness.FIT_WITH_RESTRICTIONS,
    ):
        return SuspensionAction.LIFT
    return SuspensionAction.NONE


def reason_for(contraindications: list[str]) -> MedicalSuspensionReason:
    """Suspension reason: CONTRAINDICATION when contraindications are present, else UNFIT."""
    return (
        MedicalSuspensionReason.CONTRAINDICATION
        if contraindications
        else MedicalSuspensionReason.UNFIT
    )
