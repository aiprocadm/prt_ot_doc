"""Committees срез-4 — приглашения + настраиваемый порог кворума (P10-01, TZ B.17).

Direct-handler style как в срез-3: реальная SQLite-сессия из ``sessionmaker``,
флаг committees замокан включённым, tenant — SimpleNamespace.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.api.routes import committees as routes
from app.models.committees import (
    Committee,
    CommitteeKind,
    CommitteeMeeting,
    CommitteeMeetingAttendance,
    CommitteeMember,
    CommitteeMemberRole,
    MeetingStatus,
)
from app.schemas.committees import (
    CommitteeCreate,
    CommitteeUpdate,
    InvitationBulkUpdate,
    MeetingStatusUpdate,
)

_NOW = datetime(2026, 8, 3, 10, 0, tzinfo=timezone.utc)


def _tenant(tid="tenant-1"):
    return SimpleNamespace(id=tid, is_active=True, slug="t1", code="t1")


@pytest.fixture(autouse=True)
def _flag_on(monkeypatch):
    monkeypatch.setattr(routes, "is_feature_enabled", AsyncMock(return_value=True))


async def _seed_committee(session, tenant_id, *, threshold=None, members=0):
    c = Committee(
        tenant_id=tenant_id,
        kind=CommitteeKind.OSMS,
        name="К1",
        is_active=True,
        quorum_threshold_pct=threshold,
    )
    session.add(c)
    await session.flush()
    for i in range(members):
        session.add(
            CommitteeMember(
                tenant_id=tenant_id,
                committee_id=c.id,
                person_id=f"p{i + 1}",
                role=CommitteeMemberRole.MEMBER,
            )
        )
    await session.flush()
    return c


async def _seed_meeting(session, tenant_id, committee_id, *, status=MeetingStatus.PLANNED):
    m = CommitteeMeeting(
        tenant_id=tenant_id,
        committee_id=committee_id,
        scheduled_at=_NOW,
        status=status,
    )
    session.add(m)
    await session.flush()
    return m


async def _mark_present(session, tenant_id, meeting_id, person_ids):
    for pid in person_ids:
        session.add(
            CommitteeMeetingAttendance(
                tenant_id=tenant_id, meeting_id=meeting_id, person_id=pid, present=True
            )
        )
    await session.flush()


# --- порог кворума: схема и CRUD ---------------------------------------------
def test_quorum_threshold_schema_bounds():
    with pytest.raises(ValidationError):
        CommitteeCreate(kind=CommitteeKind.OSMS, name="x", quorum_threshold_pct=150)
    with pytest.raises(ValidationError):
        CommitteeUpdate(quorum_threshold_pct=0)
    assert CommitteeCreate(kind=CommitteeKind.OSMS, name="x", quorum_threshold_pct=66)


@pytest.mark.asyncio
async def test_committee_create_and_read_threshold(sessionmaker):
    async with sessionmaker() as session:
        out = await routes.create_committee(
            payload=CommitteeCreate(kind=CommitteeKind.OSMS, name="К1", quorum_threshold_pct=66),
            tenant=_tenant(),
            session=session,
            access=SimpleNamespace(),
        )
        assert out.quorum_threshold_pct == 66
        got = await routes.get_committee(
            cid=out.id, tenant=_tenant(), session=session, access=SimpleNamespace()
        )
        assert got.quorum_threshold_pct == 66


@pytest.mark.asyncio
async def test_committee_patch_threshold_and_reset(sessionmaker):
    async with sessionmaker() as session:
        c = await _seed_committee(session, "tenant-1", threshold=66)
        out = await routes.update_committee(
            cid=c.id,
            payload=CommitteeUpdate(quorum_threshold_pct=None),
            tenant=_tenant(),
            session=session,
            access=SimpleNamespace(),
        )
        assert out.quorum_threshold_pct is None


# --- порог кворума применяется при проведении ---------------------------------
@pytest.mark.asyncio
async def test_hold_respects_configured_threshold(sessionmaker):
    """50% (включительно) — 1 из 2 достаточно; по умолчанию 1 из 2 мало."""
    async with sessionmaker() as session:
        c = await _seed_committee(session, "tenant-1", threshold=50, members=2)
        m = await _seed_meeting(session, "tenant-1", c.id)
        await _mark_present(session, "tenant-1", m.id, ["p1"])
        out = await routes.update_meeting(
            mid=m.id,
            payload=MeetingStatusUpdate(status=MeetingStatus.HELD),
            tenant=_tenant(),
            session=session,
            access=SimpleNamespace(),
        )
        assert out.status is MeetingStatus.HELD and out.quorum_met is True


@pytest.mark.asyncio
async def test_hold_default_strict_majority_still_applies(sessionmaker):
    async with sessionmaker() as session:
        c = await _seed_committee(session, "tenant-1", threshold=None, members=2)
        m = await _seed_meeting(session, "tenant-1", c.id)
        await _mark_present(session, "tenant-1", m.id, ["p1"])
        with pytest.raises(HTTPException) as exc:
            await routes.update_meeting(
                mid=m.id,
                payload=MeetingStatusUpdate(status=MeetingStatus.HELD),
                tenant=_tenant(),
                session=session,
                access=SimpleNamespace(),
            )
        assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_hold_threshold_100_requires_everyone(sessionmaker):
    async with sessionmaker() as session:
        c = await _seed_committee(session, "tenant-1", threshold=100, members=3)
        m = await _seed_meeting(session, "tenant-1", c.id)
        await _mark_present(session, "tenant-1", m.id, ["p1", "p2"])
        with pytest.raises(HTTPException) as exc:
            await routes.update_meeting(
                mid=m.id,
                payload=MeetingStatusUpdate(status=MeetingStatus.HELD),
                tenant=_tenant(),
                session=session,
                access=SimpleNamespace(),
            )
        assert exc.value.status_code == 409


# --- приглашения ---------------------------------------------------------------
@pytest.mark.asyncio
async def test_invitations_put_and_get(sessionmaker):
    async with sessionmaker() as session:
        c = await _seed_committee(session, "tenant-1")
        m = await _seed_meeting(session, "tenant-1", c.id)
        out = await routes.put_invitations(
            mid=m.id,
            payload=InvitationBulkUpdate(person_ids=["p1", "p2", "p1"]),  # дубль схлопывается
            tenant=_tenant(),
            session=session,
            access=SimpleNamespace(),
        )
        assert sorted(i.person_id for i in out) == ["p1", "p2"]
        got = await routes.get_invitations(
            mid=m.id, tenant=_tenant(), session=session, access=SimpleNamespace()
        )
        assert sorted(i.person_id for i in got) == ["p1", "p2"]
        assert all(i.invited_at is not None for i in got)


@pytest.mark.asyncio
async def test_invitations_put_replaces_set(sessionmaker):
    async with sessionmaker() as session:
        c = await _seed_committee(session, "tenant-1")
        m = await _seed_meeting(session, "tenant-1", c.id)
        await routes.put_invitations(
            mid=m.id,
            payload=InvitationBulkUpdate(person_ids=["p1", "p2"]),
            tenant=_tenant(),
            session=session,
            access=SimpleNamespace(),
        )
        out = await routes.put_invitations(
            mid=m.id,
            payload=InvitationBulkUpdate(person_ids=["p2", "p3"]),
            tenant=_tenant(),
            session=session,
            access=SimpleNamespace(),
        )
        assert sorted(i.person_id for i in out) == ["p2", "p3"]


@pytest.mark.asyncio
@pytest.mark.parametrize("mstatus", [MeetingStatus.HELD, MeetingStatus.CANCELLED])
async def test_invitations_only_for_planned(sessionmaker, mstatus):
    async with sessionmaker() as session:
        c = await _seed_committee(session, "tenant-1")
        m = await _seed_meeting(session, "tenant-1", c.id, status=mstatus)
        with pytest.raises(HTTPException) as exc:
            await routes.put_invitations(
                mid=m.id,
                payload=InvitationBulkUpdate(person_ids=["p1"]),
                tenant=_tenant(),
                session=session,
                access=SimpleNamespace(),
            )
        assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_invitations_tenant_isolation(sessionmaker):
    async with sessionmaker() as session:
        c = await _seed_committee(session, "tenant-a")
        m = await _seed_meeting(session, "tenant-a", c.id)
        with pytest.raises(HTTPException) as exc:
            await routes.get_invitations(
                mid=m.id, tenant=_tenant("tenant-b"), session=session, access=SimpleNamespace()
            )
        assert exc.value.status_code == 404
