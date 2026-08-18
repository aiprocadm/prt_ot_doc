"""Contract tests for committees срез-2 routes (mocked session, no live DB)."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api.routes import committees as routes
from app.models.committees import MeetingStatus, VoteChoice
from app.schemas.committees import (
    AttendanceBulkUpdate,
    AttendanceItem,
    MeetingStatusUpdate,
    VoteCreate,
)


@pytest.fixture(autouse=True)
def _flag_on(monkeypatch):
    """Модуль комитетов включён (канон — tests/test_committees_srez4_api.py).

    Эти тесты проверяют КОНТРАКТ ручек на замоканной сессии, а не гейт модуля
    (он покрыт отдельно в backend/tests/test_committees_flag_and_isolation.py).
    Без подмены настоящая ``is_module_enabled`` исполняется на AsyncMock-сессии:
    после волны BIZ-61 срез-3 она читает ПАРУ ``(on, expires_at)``, и распаковка
    мока падает ``ValueError: not enough values to unpack`` либо гейт отвечает
    404 вместо ожидаемого 409.
    """

    monkeypatch.setattr(routes, "is_module_enabled", AsyncMock(return_value=True))


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
    monkeypatch.setattr(
        routes,
        "_get_committee",
        AsyncMock(return_value=SimpleNamespace(id="c1", quorum_threshold_pct=None)),
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


# --- positive paths ---
@pytest.mark.asyncio
async def test_hold_with_quorum_assigns_protocol(monkeypatch):
    """PLANNED → HELD with quorum assigns protocol_seq=1 and marks quorum_met."""
    session = AsyncMock()
    session.add = MagicMock()
    # Shared result mock: feature-flag query reads .scalar_one_or_none() (truthy →
    # enabled); the protocol-seq query reads .scalars().all() (empty → seq starts 1).
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    session.execute = AsyncMock(return_value=result)
    monkeypatch.setattr(
        routes, "_get_meeting", AsyncMock(return_value=_meeting(MeetingStatus.PLANNED))
    )
    monkeypatch.setattr(
        routes,
        "_get_committee",
        AsyncMock(return_value=SimpleNamespace(id="c1", quorum_threshold_pct=None)),
    )
    monkeypatch.setattr(routes, "_count_members", AsyncMock(return_value=3))
    monkeypatch.setattr(routes, "_count_present", AsyncMock(return_value=2))  # 2*2 > 3 → quorum
    out = await routes.update_meeting(
        mid="m1",
        payload=MeetingStatusUpdate(status=MeetingStatus.HELD),
        tenant=_tenant(),
        session=session,
        access=SimpleNamespace(),
    )
    assert out.status == MeetingStatus.HELD
    assert out.protocol_seq == 1
    assert out.quorum_met is True


@pytest.mark.asyncio
async def test_attendance_dedup_idempotent(monkeypatch):
    """Regression for FIX A: a duplicated person_id collapses to one row (no 500)."""
    session = AsyncMock()
    session.add = MagicMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = []  # no existing attendance rows
    session.execute = AsyncMock(return_value=result)
    monkeypatch.setattr(
        routes, "_get_meeting", AsyncMock(return_value=_meeting(MeetingStatus.PLANNED))
    )
    monkeypatch.setattr(routes, "_committee_member_person_ids", AsyncMock(return_value={"p1"}))
    out = await routes.put_attendance(
        mid="m1",
        payload=AttendanceBulkUpdate(
            items=[
                AttendanceItem(person_id="p1", present=True),
                AttendanceItem(person_id="p1", present=False),  # duplicate → last wins
            ]
        ),
        tenant=_tenant(),
        session=session,
        access=SimpleNamespace(),
    )
    assert out == []  # get_attendance re-read yields the mocked empty set
    assert session.add.call_count == 1  # exactly one attendance row inserted, not two


@pytest.mark.asyncio
async def test_cast_vote_upsert_updates_existing(monkeypatch):
    """Re-voting updates the existing vote row in place instead of inserting a new one."""
    session = AsyncMock()
    session.add = MagicMock()
    existing_vote = SimpleNamespace(
        id="v1", decision_id="d1", person_id="p1", choice=VoteChoice.AGAINST
    )
    result = MagicMock()
    result.scalar_one_or_none.return_value = existing_vote
    session.execute = AsyncMock(return_value=result)
    monkeypatch.setattr(
        routes,
        "_get_decision",
        AsyncMock(return_value=SimpleNamespace(id="d1", meeting_id="m1", tenant_id="tenant-1")),
    )
    monkeypatch.setattr(
        routes, "_get_meeting", AsyncMock(return_value=_meeting(MeetingStatus.HELD))
    )
    monkeypatch.setattr(routes, "_is_present", AsyncMock(return_value=True))
    out = await routes.cast_vote(
        did="d1",
        payload=VoteCreate(person_id="p1", choice=VoteChoice.FOR),
        tenant=_tenant(),
        session=session,
        access=SimpleNamespace(),
    )
    assert existing_vote.choice == VoteChoice.FOR  # updated in place
    assert session.add.call_count == 0  # no new vote row
    assert out.choice == VoteChoice.FOR
