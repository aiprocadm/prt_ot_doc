"""I/O service for prescription escalation + closure-rate (TZ-3.4-V12-01)."""
from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.prescriptions.lifecycle import TERMINAL_STATES, closure_rate
from app.models.models import Prescription, PrescriptionStatus
from app.services.events import EventType
from app.services.outbox import OutboxService


async def list_overdue(
    session: AsyncSession, *, tenant_id: str, today: date
) -> list[Prescription]:
    """Tenant-scoped prescriptions past their deadline and not yet closed."""
    stmt = (
        select(Prescription)
        .where(
            Prescription.tenant_id == tenant_id,
            Prescription.deleted_at.is_(None),
            Prescription.due_at.is_not(None),
            Prescription.due_at < today,
            Prescription.status.not_in(list(TERMINAL_STATES)),
        )
        .order_by(Prescription.due_at.asc())
    )
    return list((await session.execute(stmt)).scalars().all())


async def notify_overdue(
    session: AsyncSession, *, tenant_id: str, actor_id: str | None, today: date
) -> list[Prescription]:
    """Enqueue a TASK_OVERDUE outbox event for each overdue prescription.

    The idempotency key embeds the due date, so re-running on the same day
    dedups at the destination (mirrors briefings overdue reminders).
    """
    overdue = await list_overdue(session, tenant_id=tenant_id, today=today)
    if not overdue:
        return []
    outbox = OutboxService(session)
    for p in overdue:
        await outbox.enqueue(
            tenant_id=tenant_id,
            event_type=EventType.TASK_OVERDUE.value,
            idempotency_key=f"prescription-overdue:{p.id}:{p.due_at.isoformat()}",
            payload={
                "tenant_id": tenant_id,
                "actor_id": actor_id,
                "task_id": p.id,
                "title": f"Prescription overdue: {p.description[:80]}",
                "due_at": p.due_at,
                "assignee_id": p.assignee_id,
                "status": p.status.value,
                "priority": "high",
                "overdue": True,
            },
        )
    return overdue


async def status_summary(
    session: AsyncSession, *, tenant_id: str, today: date
) -> dict[str, object]:
    """Per-status counts + overdue_count + closure_rate for a tenant."""
    rows = (
        await session.execute(
            select(Prescription.status, func.count())
            .where(
                Prescription.tenant_id == tenant_id,
                Prescription.deleted_at.is_(None),
            )
            .group_by(Prescription.status)
        )
    ).all()
    counts: dict[PrescriptionStatus, int] = {s: 0 for s in PrescriptionStatus}
    for status_value, n in rows:
        counts[PrescriptionStatus(status_value)] = int(n)

    overdue_count = await session.scalar(
        select(func.count())
        .select_from(Prescription)
        .where(
            Prescription.tenant_id == tenant_id,
            Prescription.deleted_at.is_(None),
            Prescription.due_at.is_not(None),
            Prescription.due_at < today,
            Prescription.status.not_in(list(TERMINAL_STATES)),
        )
    )
    return {
        "by_status": {s.value: counts[s] for s in PrescriptionStatus},
        "total": sum(counts.values()),
        "overdue_count": int(overdue_count or 0),
        "closure_rate": closure_rate(counts),
    }
