"""Committee execution KPIs (P10-01 срез-3, TZ B.17 «KPI исполнения»).

Aggregates over срез-1/срез-2 tables — no new storage. Attendance / quorum
rates are averaged in Python from the denormalized snapshot columns on
``committee_meeting`` (DB-agnostic: SQLite in API tests, PG16 in the db-gate).
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.committees import (
    Committee,
    CommitteeDecision,
    CommitteeDecisionTask,
    CommitteeMeeting,
    DecisionTaskStatus,
    MeetingStatus,
)
from app.schemas.committees import CommitteeKpiDto


class CommitteeKpiService:
    """Compute flat committee execution KPIs for a single tenant."""

    def __init__(self, session: AsyncSession, tenant_id: str):
        self.session = session
        self.tenant_id = tenant_id

    async def _count(self, stmt) -> int:
        return int((await self.session.execute(stmt)).scalar_one_or_none() or 0)

    async def compute(
        self, *, committee_id: str | None = None, today: date | None = None
    ) -> CommitteeKpiDto:
        today = today or date.today()

        # --- committees (soft-delete) ---
        committee_conds = [
            Committee.tenant_id == self.tenant_id,
            Committee.deleted_at.is_(None),
        ]
        if committee_id:
            committee_conds.append(Committee.id == committee_id)
        committees_total = await self._count(
            select(func.count()).select_from(Committee).where(*committee_conds)
        )
        committees_active = await self._count(
            select(func.count())
            .select_from(Committee)
            .where(*committee_conds, Committee.is_active.is_(True))
        )

        # --- meetings by status (single grouped query, soft-delete) ---
        meeting_conds = [
            CommitteeMeeting.tenant_id == self.tenant_id,
            CommitteeMeeting.deleted_at.is_(None),
        ]
        if committee_id:
            meeting_conds.append(CommitteeMeeting.committee_id == committee_id)
        by_status: dict[MeetingStatus, int] = {}
        for status_, cnt in (
            await self.session.execute(
                select(CommitteeMeeting.status, func.count())
                .where(*meeting_conds)
                .group_by(CommitteeMeeting.status)
            )
        ).all():
            by_status[status_] = int(cnt)
        meetings_planned = by_status.get(MeetingStatus.PLANNED, 0)
        meetings_held = by_status.get(MeetingStatus.HELD, 0)
        meetings_cancelled = by_status.get(MeetingStatus.CANCELLED, 0)

        # --- decisions (no soft-delete) ---
        decision_stmt = (
            select(func.count())
            .select_from(CommitteeDecision)
            .where(CommitteeDecision.tenant_id == self.tenant_id)
        )
        if committee_id:
            decision_stmt = decision_stmt.where(
                CommitteeDecision.meeting_id.in_(select(CommitteeMeeting.id).where(*meeting_conds))
            )
        decisions_total = await self._count(decision_stmt)

        # --- tasks (no soft-delete on this model → no deleted_at filter) ---
        task_conds = [CommitteeDecisionTask.tenant_id == self.tenant_id]
        if committee_id:
            task_conds.append(
                CommitteeDecisionTask.decision_id.in_(
                    select(CommitteeDecision.id).where(
                        CommitteeDecision.tenant_id == self.tenant_id,
                        CommitteeDecision.meeting_id.in_(
                            select(CommitteeMeeting.id).where(*meeting_conds)
                        ),
                    )
                )
            )
        tasks_total = await self._count(
            select(func.count()).select_from(CommitteeDecisionTask).where(*task_conds)
        )
        tasks_done = await self._count(
            select(func.count())
            .select_from(CommitteeDecisionTask)
            .where(*task_conds, CommitteeDecisionTask.status == DecisionTaskStatus.DONE)
        )
        tasks_open = await self._count(
            select(func.count())
            .select_from(CommitteeDecisionTask)
            .where(*task_conds, CommitteeDecisionTask.status != DecisionTaskStatus.DONE)
        )
        tasks_overdue = await self._count(
            select(func.count())
            .select_from(CommitteeDecisionTask)
            .where(
                *task_conds,
                CommitteeDecisionTask.status != DecisionTaskStatus.DONE,
                CommitteeDecisionTask.due_date.is_not(None),
                CommitteeDecisionTask.due_date < today,
            )
        )

        # --- attendance & quorum over held meetings (Python avg) ---
        held_rows = (
            await self.session.execute(
                select(
                    CommitteeMeeting.present_count,
                    CommitteeMeeting.members_total,
                    CommitteeMeeting.quorum_met,
                ).where(*meeting_conds, CommitteeMeeting.status == MeetingStatus.HELD)
            )
        ).all()
        held_meetings = len(held_rows)
        ratios = [
            present / members * 100.0
            for present, members, _ in held_rows
            if members and members > 0 and present is not None
        ]
        avg_attendance_pct = round(sum(ratios) / len(ratios), 1) if ratios else 0.0
        quorum_rate_pct = (
            round(sum(1 for *_, q in held_rows if q) / held_meetings * 100.0, 1)
            if held_meetings
            else 0.0
        )

        return CommitteeKpiDto(
            committees_total=committees_total,
            committees_active=committees_active,
            meetings_planned=meetings_planned,
            meetings_held=meetings_held,
            meetings_cancelled=meetings_cancelled,
            decisions_total=decisions_total,
            tasks_total=tasks_total,
            tasks_open=tasks_open,
            tasks_overdue=tasks_overdue,
            tasks_done=tasks_done,
            held_meetings=held_meetings,
            avg_attendance_pct=avg_attendance_pct,
            quorum_rate_pct=quorum_rate_pct,
        )
