"""Unit: committees service projection helpers (P10-01)."""

from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

from app.domains.committees.service import build_protocol, task_to_read
from app.models.committees import DecisionTaskStatus, MeetingStatus

TODAY = date(2026, 6, 25)


def _task(**kw):
    base = dict(
        id="t1",
        decision_id="d1",
        assignee_person_id=None,
        due_date=None,
        status=DecisionTaskStatus.OPEN,
        evidence_note=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def test_task_to_read_marks_overdue():
    t = _task(due_date=date(2026, 6, 1), status=DecisionTaskStatus.OPEN)
    read = task_to_read(t, today=TODAY)
    assert read.is_overdue is True
    assert read.status is DecisionTaskStatus.OPEN  # stored status unchanged


def test_task_to_read_done_not_overdue():
    t = _task(due_date=date(2026, 6, 1), status=DecisionTaskStatus.DONE)
    assert task_to_read(t, today=TODAY).is_overdue is False


def test_build_protocol_groups_tasks_under_decisions():
    meeting = SimpleNamespace(
        id="m1",
        committee_id="c1",
        scheduled_at=datetime(2026, 6, 20, tzinfo=timezone.utc),
        location=None,
        status=MeetingStatus.HELD,
        created_at=datetime(2026, 6, 20, tzinfo=timezone.utc),
        updated_at=datetime(2026, 6, 20, tzinfo=timezone.utc),
    )
    decision = SimpleNamespace(
        id="d1",
        meeting_id="m1",
        agenda_item_id=None,
        text="Закупить СИЗ",
        decided_at=datetime(2026, 6, 20, tzinfo=timezone.utc),
    )
    tasks = [_task(id="t1", decision_id="d1", due_date=date(2026, 6, 1))]
    proto = build_protocol(meeting, [(decision, tasks, [])], today=TODAY)
    assert proto.meeting.id == "m1"
    assert len(proto.decisions) == 1
    assert proto.decisions[0].decision.text == "Закупить СИЗ"
    assert proto.decisions[0].tasks[0].is_overdue is True
