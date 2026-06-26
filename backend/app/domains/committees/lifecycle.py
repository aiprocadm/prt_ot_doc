"""Pure-function lifecycle rules for committees срез-1.

No DB access — callers pass current/target states. Mirrors the
work_permits/ppe lifecycle style (raise a typed error; route maps to 409).
"""
from __future__ import annotations

from datetime import date

from app.models.committees import DecisionTaskStatus, MeetingStatus

#: Allowed meeting status transitions.
_ALLOWED: dict[MeetingStatus, set[MeetingStatus]] = {
    MeetingStatus.PLANNED: {MeetingStatus.HELD, MeetingStatus.CANCELLED},
    MeetingStatus.HELD: {MeetingStatus.CANCELLED},
    MeetingStatus.CANCELLED: set(),
}


class MeetingTransitionError(ValueError):
    """Raised on an illegal meeting transition or decision-on-non-held."""


def validate_meeting_transition(current: MeetingStatus, target: MeetingStatus) -> None:
    if target not in _ALLOWED.get(current, set()):
        raise MeetingTransitionError(
            f"Cannot transition meeting {current.value} -> {target.value}"
        )


def ensure_meeting_held(status: MeetingStatus) -> None:
    if status is not MeetingStatus.HELD:
        raise MeetingTransitionError(
            f"Decisions allowed only on a held meeting (status={status.value})"
        )


def is_task_overdue(
    status: DecisionTaskStatus, due_date: date | None, today: date
) -> bool:
    """A task is overdue when it has a past due_date and is not done."""
    if due_date is None or status is DecisionTaskStatus.DONE:
        return False
    return due_date < today
