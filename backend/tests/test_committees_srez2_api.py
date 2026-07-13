"""Contract tests for committees срез-2 routes (mocked session, no live DB)."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.api.routes import committees as routes
from app.models.committees import MeetingStatus, VoteChoice
from app.schemas.committees import (
    AttendanceBulkUpdate,
    AttendanceItem,
    MeetingStatusUpdate,
    VoteCreate,
)


def _tenant():
    return SimpleNamespace(id="tenant-1", is_active=True, slug="t1")


def _meeting(status=MeetingStatus.PLANNED, **kw):
    now = datetime(2026, 7, 14, tzinfo=timezone.utc)
    base = dict(
        id="m1",
        committee_id="c1",
        tenant_id="tenant-1",
        scheduled_at=now,
        location=None,
        status=status,
        held_at=None,
        protocol_seq=None,
        protocol_year=None,
        members_total=None,
        present_count=None,
        quorum_met=None,
        created_at=now,
        updated_at=now,
        deleted_at=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


@pytest.mark.asyncio
async def test_hold_without_quorum_409(monkeypatch):
    session = AsyncMock()
    monkeypatch.setattr(
        routes, "_get_meeting", AsyncMock(return_value=_meeting(MeetingStatus.PLANNED))
    )
    monkeypatch.setattr(routes, "_count_members", AsyncMock(return_value=4))
    monkeypatch.setattr(routes, "_count_present", AsyncMock(return_value=2))
    with pytest.raises(Exception) as exc:
        await routes.update_meeting(
            mid="m1",
            payload=MeetingStatusUpdate(status=MeetingStatus.HELD),
            tenant=_tenant(),
            session=session,
            access=SimpleNamespace(),
        )
    assert getattr(exc.value, "status_code", None) == 409


@pytest.mark.asyncio
async def test_vote_on_non_held_409(monkeypatch):
    session = AsyncMock()
    monkeypatch.setattr(
        routes,
        "_get_decision",
        AsyncMock(return_value=SimpleNamespace(id="d1", meeting_id="m1", tenant_id="tenant-1")),
    )
    monkeypatch.setattr(
        routes, "_get_meeting", AsyncMock(return_value=_meeting(MeetingStatus.PLANNED))
    )
    with pytest.raises(Exception) as exc:
        await routes.cast_vote(
            did="d1",
            payload=VoteCreate(person_id="p1", choice=VoteChoice.FOR),
            tenant=_tenant(),
            session=session,
            access=SimpleNamespace(),
        )
    assert getattr(exc.value, "status_code", None) == 409


@pytest.mark.asyncio
async def test_vote_absent_voter_409(monkeypatch):
    session = AsyncMock()
    monkeypatch.setattr(
        routes,
        "_get_decision",
        AsyncMock(return_value=SimpleNamespace(id="d1", meeting_id="m1", tenant_id="tenant-1")),
    )
    monkeypatch.setattr(
        routes, "_get_meeting", AsyncMock(return_value=_meeting(MeetingStatus.HELD))
    )
    monkeypatch.setattr(routes, "_is_present", AsyncMock(return_value=False))
    with pytest.raises(Exception) as exc:
        await routes.cast_vote(
            did="d1",
            payload=VoteCreate(person_id="p1", choice=VoteChoice.FOR),
            tenant=_tenant(),
            session=session,
            access=SimpleNamespace(),
        )
    assert getattr(exc.value, "status_code", None) == 409


@pytest.mark.asyncio
async def test_attendance_on_held_409(monkeypatch):
    session = AsyncMock()
    monkeypatch.setattr(
        routes, "_get_meeting", AsyncMock(return_value=_meeting(MeetingStatus.HELD))
    )
    with pytest.raises(Exception) as exc:
        await routes.put_attendance(
            mid="m1",
            payload=AttendanceBulkUpdate(items=[AttendanceItem(person_id="p1", present=True)]),
            tenant=_tenant(),
            session=session,
            access=SimpleNamespace(),
        )
    assert getattr(exc.value, "status_code", None) == 409
