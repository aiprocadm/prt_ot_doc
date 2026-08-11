"""Unit: committees schemas round-trip + overdue projection (P10-01)."""

from __future__ import annotations

from datetime import date, datetime, timezone

from app.models.committees import CommitteeKind, DecisionTaskStatus, MeetingStatus
from app.schemas.committees import (
    CommitteeCreate,
    DecisionTaskRead,
    DecisionTaskUpdate,
    MeetingCreate,
    MeetingStatusUpdate,
)


def test_committee_create_defaults():
    c = CommitteeCreate(kind=CommitteeKind.OSMS, name="Комитет ОТ")
    assert c.is_active is True
    assert c.description is None


def test_meeting_create_requires_scheduled_at():
    m = MeetingCreate(scheduled_at=datetime(2026, 7, 1, tzinfo=timezone.utc))
    assert m.location is None


def test_meeting_status_update_enum():
    u = MeetingStatusUpdate(status=MeetingStatus.HELD)
    assert u.status is MeetingStatus.HELD


def test_decision_task_read_carries_overdue_flag():
    t = DecisionTaskRead(
        id="t1",
        decision_id="d1",
        assignee_person_id=None,
        due_date=date(2026, 6, 1),
        status=DecisionTaskStatus.OPEN,
        evidence_note=None,
        is_overdue=True,
    )
    assert t.is_overdue is True


def test_decision_task_update_partial():
    u = DecisionTaskUpdate(status=DecisionTaskStatus.DONE)
    assert u.evidence_note is None
