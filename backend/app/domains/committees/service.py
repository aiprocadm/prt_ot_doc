"""Read-projection + mapping helpers for committees срез-1/срез-2 (P10-01).

Kept DB-agnostic where possible: ``task_to_read`` / ``build_protocol`` /
``vote_summary`` take already-loaded ORM rows (or SimpleNamespace in tests)
so the overdue/vote-tally projections and protocol grouping are
unit-testable without a session.
"""

from __future__ import annotations

from datetime import date

from app.domains.committees.lifecycle import decision_outcome, is_task_overdue, tally_votes
from app.schemas.committees import (
    DecisionRead,
    DecisionTaskRead,
    DecisionVoteSummary,
    MeetingRead,
    ProtocolDecision,
    ProtocolRead,
    VoteRead,
)


def _today() -> date:
    return date.today()


def task_to_read(task, *, today: date | None = None) -> DecisionTaskRead:
    today = today or _today()
    return DecisionTaskRead(
        id=task.id,
        decision_id=task.decision_id,
        assignee_person_id=task.assignee_person_id,
        due_date=task.due_date,
        status=task.status,
        evidence_note=task.evidence_note,
        is_overdue=is_task_overdue(task.status, task.due_date, today),
    )


def vote_summary(decision_id: str, votes) -> DecisionVoteSummary:
    """Tally raw vote rows into a ``DecisionVoteSummary`` projection."""
    choices = [v.choice for v in votes]
    votes_for, votes_against, votes_abstain = tally_votes(choices)
    outcome = decision_outcome(votes_for, votes_against).value if votes else None
    return DecisionVoteSummary(
        decision_id=decision_id,
        votes_for=votes_for,
        votes_against=votes_against,
        votes_abstain=votes_abstain,
        outcome=outcome,
        votes=[VoteRead.model_validate(v, from_attributes=True) for v in votes],
    )


def build_protocol(meeting, decisions_with_votes, *, today: date | None = None) -> ProtocolRead:
    """decisions_with_votes: iterable of ``(decision_row, [task_rows], [vote_rows])``."""
    today = today or _today()
    grouped = []
    for decision, tasks, votes in decisions_with_votes:
        choices = [v.choice for v in votes]
        votes_for, votes_against, votes_abstain = tally_votes(choices)
        grouped.append(
            ProtocolDecision(
                decision=DecisionRead.model_validate(decision, from_attributes=True),
                tasks=[task_to_read(t, today=today) for t in tasks],
                votes_for=votes_for,
                votes_against=votes_against,
                votes_abstain=votes_abstain,
                outcome=decision_outcome(votes_for, votes_against).value if votes else None,
                votes=[VoteRead.model_validate(v, from_attributes=True) for v in votes],
            )
        )
    return ProtocolRead(
        meeting=MeetingRead.model_validate(meeting, from_attributes=True),
        decisions=grouped,
    )
