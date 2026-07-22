"""Committees срез-3 — projection into the Command Center (P10-01).

Covers ``OperationalDashboardService._get_committee_task_alerts``: overdue tasks
surface as a HIGH ``committee_task`` alert, unassigned open tasks as MEDIUM,
DONE/assigned tasks never surface, and the source is tenant-scoped.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from app.core.config import Settings
from app.models.committees import (
    Committee,
    CommitteeDecision,
    CommitteeDecisionTask,
    CommitteeKind,
    CommitteeMeeting,
    DecisionTaskStatus,
    MeetingStatus,
)
from app.modules.operational_dashboard.schemas import AlertCategory, AlertSeverity
from app.modules.operational_dashboard.service import OperationalDashboardService

_NOW = datetime(2026, 7, 22, 10, 0, tzinfo=timezone.utc)
_TODAY = date.today()


async def _make_task(session, tenant_id, *, status, due_date=None, assignee=None):
    c = Committee(tenant_id=tenant_id, kind=CommitteeKind.OSMS, name="К")
    session.add(c)
    await session.flush()
    m = CommitteeMeeting(
        tenant_id=tenant_id, committee_id=c.id, scheduled_at=_NOW, status=MeetingStatus.HELD
    )
    session.add(m)
    await session.flush()
    d = CommitteeDecision(tenant_id=tenant_id, meeting_id=m.id, text="Р")
    session.add(d)
    await session.flush()
    t = CommitteeDecisionTask(
        tenant_id=tenant_id,
        decision_id=d.id,
        status=status,
        due_date=due_date,
        assignee_person_id=assignee,
    )
    session.add(t)
    await session.flush()
    return t


def _service():
    return OperationalDashboardService(Settings())


def _by_id(alerts):
    return {a.id: a for a in alerts}


@pytest.mark.asyncio
async def test_no_committee_data_no_alerts(sessionmaker):
    async with sessionmaker() as session:
        alerts = await _service()._get_committee_task_alerts("empty-tenant", session)
    assert alerts == []


@pytest.mark.asyncio
async def test_overdue_task_high_alert(sessionmaker):
    async with sessionmaker() as session:
        await _make_task(
            session,
            "t1",
            status=DecisionTaskStatus.OPEN,
            due_date=_TODAY - timedelta(days=2),
            assignee="p1",
        )
        await session.commit()
        alerts = await _service()._get_committee_task_alerts("t1", session)

    found = _by_id(alerts)
    assert "committee_tasks_overdue" in found
    a = found["committee_tasks_overdue"]
    assert a.category == AlertCategory.COMMITTEE_TASK
    assert a.severity == AlertSeverity.HIGH
    assert a.count == 1
    assert a.action_url == "/committees"


@pytest.mark.asyncio
async def test_unassigned_task_medium_alert(sessionmaker):
    async with sessionmaker() as session:
        await _make_task(
            session,
            "t1",
            status=DecisionTaskStatus.OPEN,
            due_date=_TODAY + timedelta(days=5),  # future → not overdue
            assignee=None,
        )
        await session.commit()
        alerts = await _service()._get_committee_task_alerts("t1", session)

    found = _by_id(alerts)
    assert "committee_tasks_unassigned" in found
    assert found["committee_tasks_unassigned"].severity == AlertSeverity.MEDIUM
    assert "committee_tasks_overdue" not in found  # future due date


@pytest.mark.asyncio
async def test_done_and_assigned_excluded(sessionmaker):
    async with sessionmaker() as session:
        # DONE + past due → not overdue.
        await _make_task(
            session,
            "t1",
            status=DecisionTaskStatus.DONE,
            due_date=_TODAY - timedelta(days=10),
            assignee=None,
        )
        # Assigned + future → neither overdue nor unassigned.
        await _make_task(
            session,
            "t1",
            status=DecisionTaskStatus.IN_PROGRESS,
            due_date=_TODAY + timedelta(days=10),
            assignee="p9",
        )
        await session.commit()
        alerts = await _service()._get_committee_task_alerts("t1", session)

    assert alerts == []


@pytest.mark.asyncio
async def test_committee_task_alerts_tenant_isolation(sessionmaker):
    async with sessionmaker() as session:
        await _make_task(
            session,
            "tenant-b",
            status=DecisionTaskStatus.OPEN,
            due_date=_TODAY - timedelta(days=1),
            assignee=None,
        )
        await session.commit()
        alerts = await _service()._get_committee_task_alerts("tenant-a", session)

    assert alerts == []
