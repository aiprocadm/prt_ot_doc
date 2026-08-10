"""Committees срез-3 — KPI service + /committees/kpi route (P10-01, TZ B.17).

Service-level assertions run against the in-memory SQLite session (real
aggregation SQL). Route-level assertions cover the срез-3 wrappers: feature
flag 404, ETag/304, and management-vs-worker RBAC end-to-end.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.api.routes import committees as routes
from app.domains.committees.kpi import CommitteeKpiService
from app.models.committees import (
    Committee,
    CommitteeDecision,
    CommitteeDecisionTask,
    CommitteeKind,
    CommitteeMeeting,
    DecisionTaskStatus,
    MeetingStatus,
)
from app.models.tenant_billing import RoleEnum

_NOW = datetime(2026, 7, 22, 10, 0, tzinfo=timezone.utc)
_TODAY = date(2026, 7, 22)


# --- seeding helpers (FK enforcement is off in the SQLite test DB) ------------
async def _add_committee(session, tenant_id, *, active=True, name="К1"):
    c = Committee(tenant_id=tenant_id, kind=CommitteeKind.OSMS, name=name, is_active=active)
    session.add(c)
    await session.flush()
    return c


async def _add_meeting(
    session,
    tenant_id,
    committee_id,
    *,
    status=MeetingStatus.PLANNED,
    members_total=None,
    present_count=None,
    quorum_met=None,
):
    m = CommitteeMeeting(
        tenant_id=tenant_id,
        committee_id=committee_id,
        scheduled_at=_NOW,
        status=status,
        members_total=members_total,
        present_count=present_count,
        quorum_met=quorum_met,
    )
    session.add(m)
    await session.flush()
    return m


async def _add_decision(session, tenant_id, meeting_id, *, text="Решение"):
    d = CommitteeDecision(tenant_id=tenant_id, meeting_id=meeting_id, text=text)
    session.add(d)
    await session.flush()
    return d


async def _add_task(
    session,
    tenant_id,
    decision_id,
    *,
    status=DecisionTaskStatus.OPEN,
    due_date=None,
    assignee_person_id=None,
):
    t = CommitteeDecisionTask(
        tenant_id=tenant_id,
        decision_id=decision_id,
        status=status,
        due_date=due_date,
        assignee_person_id=assignee_person_id,
    )
    session.add(t)
    await session.flush()
    return t


# --- service-level tests ------------------------------------------------------
@pytest.mark.asyncio
async def test_kpi_empty_tenant_all_zeros(sessionmaker):
    async with sessionmaker() as session:
        kpi = await CommitteeKpiService(session, "empty-tenant").compute(today=_TODAY)
    assert kpi.committees_total == 0
    assert kpi.meetings_held == 0
    assert kpi.decisions_total == 0
    assert kpi.tasks_total == 0
    # No held meetings → rates default to 0.0, no ZeroDivisionError.
    assert kpi.held_meetings == 0
    assert kpi.avg_attendance_pct == 0.0
    assert kpi.quorum_rate_pct == 0.0


@pytest.mark.asyncio
async def test_kpi_counts_across_entities(sessionmaker):
    async with sessionmaker() as session:
        c = await _add_committee(session, "t1", active=True)
        await _add_committee(session, "t1", active=False, name="К-архив")
        await _add_meeting(session, "t1", c.id, status=MeetingStatus.PLANNED)
        held = await _add_meeting(
            session,
            "t1",
            c.id,
            status=MeetingStatus.HELD,
            members_total=4,
            present_count=3,
            quorum_met=True,
        )
        await _add_meeting(session, "t1", c.id, status=MeetingStatus.CANCELLED)
        d = await _add_decision(session, "t1", held.id)
        await _add_task(session, "t1", d.id, status=DecisionTaskStatus.OPEN)
        await _add_task(session, "t1", d.id, status=DecisionTaskStatus.DONE)
        await session.commit()

        kpi = await CommitteeKpiService(session, "t1").compute(today=_TODAY)

    assert kpi.committees_total == 2
    assert kpi.committees_active == 1
    assert kpi.meetings_planned == 1
    assert kpi.meetings_held == 1
    assert kpi.meetings_cancelled == 1
    assert kpi.decisions_total == 1
    assert kpi.tasks_total == 2
    assert kpi.tasks_done == 1
    assert kpi.tasks_open == 1


@pytest.mark.asyncio
async def test_kpi_soft_deleted_committee_excluded(sessionmaker):
    async with sessionmaker() as session:
        await _add_committee(session, "t1", name="живой")
        dead = await _add_committee(session, "t1", name="удалённый")
        dead.deleted_at = _NOW
        await session.commit()

        kpi = await CommitteeKpiService(session, "t1").compute(today=_TODAY)
    assert kpi.committees_total == 1


@pytest.mark.asyncio
async def test_kpi_tasks_fsm_overdue_and_open(sessionmaker):
    """Overdue/open count by FSM status; DONE never counts even if past due."""
    async with sessionmaker() as session:
        c = await _add_committee(session, "t1")
        m = await _add_meeting(session, "t1", c.id, status=MeetingStatus.HELD)
        d = await _add_decision(session, "t1", m.id)
        past = _TODAY - timedelta(days=3)
        future = _TODAY + timedelta(days=3)
        await _add_task(session, "t1", d.id, status=DecisionTaskStatus.OPEN, due_date=past)
        await _add_task(session, "t1", d.id, status=DecisionTaskStatus.IN_PROGRESS, due_date=future)
        await _add_task(session, "t1", d.id, status=DecisionTaskStatus.OPEN, due_date=None)
        # DONE + past due must NOT be counted as overdue or open.
        await _add_task(session, "t1", d.id, status=DecisionTaskStatus.DONE, due_date=past)
        await session.commit()

        kpi = await CommitteeKpiService(session, "t1").compute(today=_TODAY)

    assert kpi.tasks_total == 4
    assert kpi.tasks_done == 1
    assert kpi.tasks_open == 3  # OPEN + IN_PROGRESS + OPEN(no due)
    assert kpi.tasks_overdue == 1  # only the past-due OPEN


@pytest.mark.asyncio
async def test_kpi_attendance_and_quorum_rates(sessionmaker):
    """avg_attendance/quorum_rate averaged over HELD meetings only."""
    async with sessionmaker() as session:
        c = await _add_committee(session, "t1")
        # 3/4 = 75%, quorum True
        await _add_meeting(
            session,
            "t1",
            c.id,
            status=MeetingStatus.HELD,
            members_total=4,
            present_count=3,
            quorum_met=True,
        )
        # 1/2 = 50%, quorum False
        await _add_meeting(
            session,
            "t1",
            c.id,
            status=MeetingStatus.HELD,
            members_total=2,
            present_count=1,
            quorum_met=False,
        )
        # PLANNED meeting must be ignored by both rates.
        await _add_meeting(
            session,
            "t1",
            c.id,
            status=MeetingStatus.PLANNED,
            members_total=10,
            present_count=0,
        )
        await session.commit()

        kpi = await CommitteeKpiService(session, "t1").compute(today=_TODAY)

    assert kpi.held_meetings == 2
    assert kpi.avg_attendance_pct == 62.5  # (75 + 50) / 2
    assert kpi.quorum_rate_pct == 50.0  # 1 of 2 held meetings met quorum


@pytest.mark.asyncio
async def test_kpi_committee_id_filter_isolates(sessionmaker):
    async with sessionmaker() as session:
        c1 = await _add_committee(session, "t1", name="К1")
        c2 = await _add_committee(session, "t1", name="К2")
        m1 = await _add_meeting(session, "t1", c1.id, status=MeetingStatus.HELD)
        await _add_meeting(session, "t1", c2.id, status=MeetingStatus.HELD)
        d1 = await _add_decision(session, "t1", m1.id)
        await _add_task(session, "t1", d1.id, status=DecisionTaskStatus.OPEN)
        await session.commit()

        only_c1 = await CommitteeKpiService(session, "t1").compute(committee_id=c1.id, today=_TODAY)
    assert only_c1.committees_total == 1
    assert only_c1.meetings_held == 1  # c2's held meeting excluded
    assert only_c1.decisions_total == 1
    assert only_c1.tasks_total == 1


@pytest.mark.asyncio
async def test_kpi_tenant_isolation(sessionmaker):
    async with sessionmaker() as session:
        ca = await _add_committee(session, "tenant-a")
        await _add_meeting(session, "tenant-a", ca.id, status=MeetingStatus.HELD)
        cb = await _add_committee(session, "tenant-b")
        await _add_meeting(session, "tenant-b", cb.id, status=MeetingStatus.HELD)
        await _add_meeting(session, "tenant-b", cb.id, status=MeetingStatus.HELD)
        await session.commit()

        kpi_a = await CommitteeKpiService(session, "tenant-a").compute(today=_TODAY)
    assert kpi_a.committees_total == 1
    assert kpi_a.meetings_held == 1  # tenant-b's two held meetings are invisible


# --- route-level tests (срез-3 wrappers) --------------------------------------
def _tenant():
    return SimpleNamespace(id="tenant-1", is_active=True, slug="t1", code="t1")


@pytest.mark.asyncio
async def test_kpi_route_flag_off_returns_404(monkeypatch):
    from fastapi import Response

    monkeypatch.setattr(routes, "is_module_enabled", AsyncMock(return_value=False))
    with pytest.raises(Exception) as exc:
        await routes.committee_kpi(
            request=SimpleNamespace(headers={}),
            response=Response(),
            tenant=_tenant(),
            session=AsyncMock(),
            access=SimpleNamespace(),
            committee_id=None,
        )
    assert getattr(exc.value, "status_code", None) == 404


@pytest.mark.asyncio
async def test_kpi_route_etag_304(monkeypatch):
    from fastapi import Response

    from app.schemas.committees import CommitteeKpiDto

    monkeypatch.setattr(routes, "is_module_enabled", AsyncMock(return_value=True))
    monkeypatch.setattr(
        routes.CommitteeKpiService,
        "compute",
        AsyncMock(return_value=CommitteeKpiDto(committees_total=2, meetings_held=1)),
    )

    # First call: no If-None-Match → full DTO, ETag header set.
    resp1 = Response()
    out1 = await routes.committee_kpi(
        request=SimpleNamespace(headers={}),
        response=resp1,
        tenant=_tenant(),
        session=AsyncMock(),
        access=SimpleNamespace(),
        committee_id=None,
    )
    etag = resp1.headers["etag"]
    assert isinstance(out1, CommitteeKpiDto)
    assert out1.committees_total == 2

    # Second call: matching If-None-Match → 304, no body.
    out2 = await routes.committee_kpi(
        request=SimpleNamespace(headers={"if-none-match": etag}),
        response=Response(),
        tenant=_tenant(),
        session=AsyncMock(),
        access=SimpleNamespace(),
        committee_id=None,
    )
    assert getattr(out2, "status_code", None) == 304


# --- end-to-end RBAC (management passes, worker forbidden) ---------------------
@pytest.mark.asyncio
async def test_kpi_rbac_management_vs_worker(async_client, make_auth_headers, monkeypatch):
    # Flag defaults off for committees → force it on so the handler body runs.
    monkeypatch.setattr(routes, "is_module_enabled", AsyncMock(return_value=True))

    hr_headers = await make_auth_headers(RoleEnum.HR)
    resp_mgmt = await async_client.get("/api/v1/committees/kpi", headers=hr_headers)
    assert resp_mgmt.status_code == 200
    assert "committees_total" in resp_mgmt.json()

    worker_headers = await make_auth_headers(RoleEnum.WORKER)
    resp_worker = await async_client.get("/api/v1/committees/kpi", headers=worker_headers)
    assert resp_worker.status_code == 403
