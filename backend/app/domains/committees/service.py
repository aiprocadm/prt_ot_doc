"""Read-projection + mapping helpers for committees срез-1 (P10-01).

Kept DB-agnostic where possible: ``task_to_read`` / ``build_protocol`` take
already-loaded ORM rows (or SimpleNamespace in tests) so the overdue
projection and protocol grouping are unit-testable without a session.
"""

from __future__ import annotations

from datetime import date

from app.domains.committees.lifecycle import is_task_overdue
from app.schemas.committees import (
    DecisionRead,
    DecisionTaskRead,
    MeetingRead,
    ProtocolDecision,
    ProtocolRead,
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


def build_protocol(meeting, decisions_with_tasks, *, today: date | None = None) -> ProtocolRead:
    """decisions_with_tasks: iterable of ``(decision_row, [task_rows])``."""
    today = today or _today()
    grouped = [
        ProtocolDecision(
            decision=DecisionRead.model_validate(decision, from_attributes=True),
            tasks=[task_to_read(t, today=today) for t in tasks],
        )
        for decision, tasks in decisions_with_tasks
    ]
    return ProtocolRead(
        meeting=MeetingRead.model_validate(meeting, from_attributes=True),
        decisions=grouped,
    )
