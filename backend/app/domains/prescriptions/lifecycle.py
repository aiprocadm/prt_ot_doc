"""Prescription status lifecycle — pure FSM (no DB / no app imports).

TZ-3.4-V12-01. Linear + rework loop:
OPEN -> IN_PROGRESS -> COMPLETED -> VERIFIED (terminal); COMPLETED -> IN_PROGRESS
on a failed re-inspection; CANCELLED reachable only from OPEN/IN_PROGRESS;
VERIFIED/CANCELLED terminal. A self-transition is an idempotent no-op.
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import date

from app.models.models import PrescriptionStatus

_S = PrescriptionStatus

ALLOWED_TRANSITIONS: dict[PrescriptionStatus, frozenset[PrescriptionStatus]] = {
    _S.OPEN: frozenset({_S.IN_PROGRESS, _S.CANCELLED}),
    _S.IN_PROGRESS: frozenset({_S.COMPLETED, _S.CANCELLED}),
    _S.COMPLETED: frozenset({_S.VERIFIED, _S.IN_PROGRESS}),
    _S.VERIFIED: frozenset(),
    _S.CANCELLED: frozenset(),
}

TERMINAL_STATES: frozenset[PrescriptionStatus] = frozenset({_S.VERIFIED, _S.CANCELLED})

# Segregation of duties: only these roles may move a prescription to VERIFIED.
VERIFY_ROLES: frozenset[str] = frozenset({"admin", "owner"})


class InvalidTransition(Exception):
    """Raised when a status transition is not permitted by the FSM."""

    def __init__(self, current: PrescriptionStatus, target: PrescriptionStatus) -> None:
        self.current = current
        self.target = target
        super().__init__(
            f"Cannot transition prescription from {current.value} to {target.value}"
        )


def validate_transition(current: PrescriptionStatus, target: PrescriptionStatus) -> None:
    """Raise :class:`InvalidTransition` unless ``target`` is reachable from
    ``current``. A self-transition (``current == target``) is always allowed."""
    if current == target:
        return
    if target not in ALLOWED_TRANSITIONS[current]:
        raise InvalidTransition(current, target)


def is_terminal(status: PrescriptionStatus) -> bool:
    return status in TERMINAL_STATES


def requires_evidence(target: PrescriptionStatus) -> bool:
    return target == PrescriptionStatus.COMPLETED


def is_overdue(due_at: date | None, status: PrescriptionStatus, today: date) -> bool:
    """True when the prescription is past its deadline and not yet closed.

    Terminal states (VERIFIED, CANCELLED) are never overdue. A COMPLETED row
    past its deadline IS overdue — work is done but not yet verified/closed.
    ``today`` is injected so callers/tests stay deterministic.
    """
    return due_at is not None and due_at < today and status not in TERMINAL_STATES


def closure_rate(counts: Mapping[PrescriptionStatus, int]) -> float:
    """(VERIFIED + COMPLETED) / total ; 0.0 when there are no prescriptions."""
    total = sum(counts.values())
    if total == 0:
        return 0.0
    closed = counts.get(PrescriptionStatus.VERIFIED, 0) + counts.get(PrescriptionStatus.COMPLETED, 0)
    return closed / total
