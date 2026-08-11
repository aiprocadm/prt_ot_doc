"""Unit: committees lifecycle guards + overdue computation (P10-01)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.domains.committees.lifecycle import (
    MeetingTransitionError,
    ensure_meeting_held,
    is_task_overdue,
    validate_meeting_transition,
)
from app.models.committees import DecisionTaskStatus, MeetingStatus

TODAY = date(2026, 6, 25)


def test_planned_to_held_allowed():
    validate_meeting_transition(MeetingStatus.PLANNED, MeetingStatus.HELD)


def test_planned_to_cancelled_allowed():
    validate_meeting_transition(MeetingStatus.PLANNED, MeetingStatus.CANCELLED)


def test_held_to_cancelled_allowed():
    validate_meeting_transition(MeetingStatus.HELD, MeetingStatus.CANCELLED)


def test_held_to_planned_rejected():
    with pytest.raises(MeetingTransitionError):
        validate_meeting_transition(MeetingStatus.HELD, MeetingStatus.PLANNED)


def test_cancelled_is_terminal():
    with pytest.raises(MeetingTransitionError):
        validate_meeting_transition(MeetingStatus.CANCELLED, MeetingStatus.HELD)


def test_decision_requires_held_meeting():
    ensure_meeting_held(MeetingStatus.HELD)  # no raise
    with pytest.raises(MeetingTransitionError):
        ensure_meeting_held(MeetingStatus.PLANNED)


def test_overdue_true_when_past_due_and_open():
    assert is_task_overdue(DecisionTaskStatus.OPEN, TODAY - timedelta(days=1), TODAY) is True


def test_overdue_false_when_done():
    assert is_task_overdue(DecisionTaskStatus.DONE, TODAY - timedelta(days=5), TODAY) is False


def test_overdue_false_when_no_due_date():
    assert is_task_overdue(DecisionTaskStatus.OPEN, None, TODAY) is False


def test_overdue_false_when_due_today():
    assert is_task_overdue(DecisionTaskStatus.OPEN, TODAY, TODAY) is False
