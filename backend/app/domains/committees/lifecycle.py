"""Pure-function lifecycle rules for committees срез-1.

No DB access — callers pass current/target states. Mirrors the
work_permits/ppe lifecycle style (raise a typed error; route maps to 409).
"""

from __future__ import annotations

import enum
from collections.abc import Iterable
from datetime import date

from app.models.committees import DecisionTaskStatus, MeetingStatus, VoteChoice

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
        raise MeetingTransitionError(f"Cannot transition meeting {current.value} -> {target.value}")


def ensure_meeting_held(status: MeetingStatus) -> None:
    if status is not MeetingStatus.HELD:
        raise MeetingTransitionError(
            f"Decisions allowed only on a held meeting (status={status.value})"
        )


def is_task_overdue(status: DecisionTaskStatus, due_date: date | None, today: date) -> bool:
    """A task is overdue when it has a past due_date and is not done."""
    if due_date is None or status is DecisionTaskStatus.DONE:
        return False
    return due_date < today


class DecisionOutcome(str, enum.Enum):
    CARRIED = "carried"
    REJECTED = "rejected"


def is_quorum(members_total: int, present_count: int) -> bool:
    """Quorum = strictly more than half of active members present."""
    if members_total <= 0:
        return False
    return present_count * 2 > members_total


def tally_votes(choices: Iterable[VoteChoice]) -> tuple[int, int, int]:
    """Return (for, against, abstain) counts."""
    votes_for = votes_against = votes_abstain = 0
    for c in choices:
        if c is VoteChoice.FOR:
            votes_for += 1
        elif c is VoteChoice.AGAINST:
            votes_against += 1
        else:
            votes_abstain += 1
    return votes_for, votes_against, votes_abstain


def decision_outcome(votes_for: int, votes_against: int) -> DecisionOutcome:
    """Carried iff for > against (tie → rejected; abstentions excluded)."""
    return DecisionOutcome.CARRIED if votes_for > votes_against else DecisionOutcome.REJECTED


def next_protocol_seq(existing_seqs: Iterable[int]) -> int:
    """Next sequential protocol number within a committee/year."""
    return max(existing_seqs, default=0) + 1


def validate_hold(current: MeetingStatus, quorum_met: bool) -> None:
    """Holding a meeting requires a legal transition AND quorum."""
    validate_meeting_transition(current, MeetingStatus.HELD)
    if not quorum_met:
        raise MeetingTransitionError("Cannot hold meeting without quorum")


def ensure_can_vote(meeting_status: MeetingStatus) -> None:
    if meeting_status is not MeetingStatus.HELD:
        raise MeetingTransitionError(
            f"Voting allowed only on a held meeting (status={meeting_status.value})"
        )
