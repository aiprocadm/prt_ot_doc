"""Task orchestration for deadlines and obligations."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Iterable

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import (
    Attestation,
    Inspection,
    Prescription,
    Tenant,
    TrainingCourse,
    TrainingPlan,
)
from app.models.obligations import Task, TaskPriority, TaskReminderChannel, TaskStatus
from app.services.events import EventType
from app.services.outbox import OutboxService


def _due_datetime(value: date | datetime | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    return datetime.combine(value, time(hour=23, minute=59), tzinfo=timezone.utc)


DEFAULT_REMINDER_DAYS = (30, 14, 7, 2)


def _normalize_reminder_days(values: Iterable[int] | None) -> list[int]:
    if not values:
        return list(DEFAULT_REMINDER_DAYS)
    normalized: list[int] = []
    for value in values:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            continue
        if parsed <= 0:
            continue
        if parsed not in normalized:
            normalized.append(parsed)
    return normalized or list(DEFAULT_REMINDER_DAYS)


def _next_reminder(
    due_at: datetime | None,
    *,
    reminder_days: Iterable[int] | None = None,
    now: datetime | None = None,
) -> datetime | None:
    if due_at is None:
        return None
    now = now or datetime.now(timezone.utc)
    if due_at <= now:
        return now
    offsets = _normalize_reminder_days(reminder_days)
    candidates = [due_at - timedelta(days=days) for days in offsets]
    candidates.append(due_at)
    upcoming = [candidate for candidate in candidates if candidate > now]
    if not upcoming:
        return due_at
    return min(upcoming)


def _next_reminder_after_send(
    due_at: datetime | None,
    *,
    reminder_days: Iterable[int] | None = None,
    now: datetime,
) -> datetime | None:
    if due_at is None:
        return None
    if due_at <= now:
        return now + timedelta(days=1)
    return _next_reminder(due_at, reminder_days=reminder_days, now=now)


async def _get_reminder_days(session: AsyncSession) -> list[int]:
    tenant_id = str(session.info.get("tenant_id") or "").strip() or None
    tenant_slug = (
        str(session.info.get("tenant_slug") or session.info.get("tenant") or "").strip() or None
    )
    if tenant_id:
        stmt = select(Tenant).where(Tenant.id == tenant_id)
    elif tenant_slug:
        stmt = select(Tenant).where(or_(Tenant.slug == tenant_slug, Tenant.code == tenant_slug))
    else:
        return list(DEFAULT_REMINDER_DAYS)
    tenant = (await session.execute(stmt)).scalar_one_or_none()
    settings = tenant.settings if tenant and isinstance(tenant.settings, dict) else {}
    obligations = settings.get("obligations") if isinstance(settings, dict) else {}
    reminder_days = None
    if isinstance(obligations, dict):
        reminder_days = obligations.get("reminder_days")
    return _normalize_reminder_days(reminder_days)


async def next_task_reminder(session: AsyncSession, *, due_at: datetime | None) -> datetime | None:
    reminder_days = await _get_reminder_days(session)
    return _next_reminder(due_at, reminder_days=reminder_days)


async def create_training_task(
    session: AsyncSession,
    *,
    tenant_id: str,
    plan: TrainingPlan,
    course: TrainingCourse,
    actor_id: str | None,
) -> Task:
    due_at = _due_datetime(plan.due_date)
    reminder_days = await _get_reminder_days(session)
    task = Task(
        tenant_id=tenant_id,
        title=f"Complete training: {course.title}",
        description=f"Training plan {plan.id} requires completion.",
        entity_type="training_plan",
        entity_id=plan.id,
        due_at=due_at,
        status=TaskStatus.OPEN,
        assignee_id=None,
        created_by=actor_id,
        priority=TaskPriority.MEDIUM,
        reminder_channel=TaskReminderChannel.IN_APP,
        next_remind_at=_next_reminder(due_at, reminder_days=reminder_days),
    )
    session.add(task)
    await session.flush()
    return task


async def create_medical_task(
    session: AsyncSession,
    *,
    tenant_id: str,
    person_id: str,
    due_date: date | None,
    actor_id: str | None,
) -> Task:
    due_at = _due_datetime(due_date)
    reminder_days = await _get_reminder_days(session)
    task = Task(
        tenant_id=tenant_id,
        title="Medical exam required",
        description="Schedule and complete the required medical exam.",
        entity_type="medical_requirement",
        entity_id=person_id,
        due_at=due_at,
        status=TaskStatus.OPEN,
        assignee_id=None,
        created_by=actor_id,
        priority=TaskPriority.HIGH,
        reminder_channel=TaskReminderChannel.IN_APP,
        next_remind_at=_next_reminder(due_at, reminder_days=reminder_days),
    )
    session.add(task)
    await session.flush()
    return task


async def upsert_inspection_task(
    session: AsyncSession,
    *,
    tenant_id: str,
    inspection: Inspection,
    actor_id: str | None,
) -> Task:
    reminder_days = await _get_reminder_days(session)
    due_at = _due_datetime(inspection.scheduled_at)
    stmt = select(Task).where(
        Task.tenant_id == tenant_id,
        Task.entity_type == "inspection",
        Task.entity_id == inspection.id,
    )
    task = (await session.execute(stmt)).scalar_one_or_none()
    if task is None:
        task = Task(
            tenant_id=tenant_id,
            title=f"Inspection due: {inspection.authority}",
            description=inspection.purpose,
            entity_type="inspection",
            entity_id=inspection.id,
            status=TaskStatus.OPEN,
            created_by=actor_id,
            priority=TaskPriority.HIGH,
            reminder_channel=TaskReminderChannel.IN_APP,
        )
        session.add(task)

    task.title = f"Inspection due: {inspection.authority}"
    task.description = inspection.purpose
    task.due_at = due_at
    task.assignee_id = inspection.responsible_id
    task.next_remind_at = _next_reminder(due_at, reminder_days=reminder_days)
    await session.flush()
    return task


async def upsert_attestation_task(
    session: AsyncSession,
    *,
    tenant_id: str,
    attestation: Attestation,
    actor_id: str | None,
) -> Task:
    reminder_days = await _get_reminder_days(session)
    due_at = _due_datetime(attestation.expires_at)
    stmt = select(Task).where(
        Task.tenant_id == tenant_id,
        Task.entity_type == "attestation",
        Task.entity_id == attestation.id,
    )
    task = (await session.execute(stmt)).scalar_one_or_none()
    if task is None:
        task = Task(
            tenant_id=tenant_id,
            title=f"Attestation renewal: {attestation.name}",
            description="Employee attestation renewal required.",
            entity_type="attestation",
            entity_id=attestation.id,
            status=TaskStatus.OPEN,
            created_by=actor_id,
            priority=TaskPriority.MEDIUM,
            reminder_channel=TaskReminderChannel.IN_APP,
        )
        session.add(task)

    task.title = f"Attestation renewal: {attestation.name}"
    task.due_at = due_at
    task.assignee_id = attestation.responsible_id
    task.next_remind_at = _next_reminder(due_at, reminder_days=reminder_days)
    await session.flush()
    return task


async def process_task_reminders(
    session: AsyncSession,
    *,
    now: datetime | None = None,
) -> int:
    now = now or datetime.now(timezone.utc)
    reminder_days = await _get_reminder_days(session)
    stmt = (
        select(Task)
        .where(
            Task.status.in_([TaskStatus.OPEN, TaskStatus.IN_PROGRESS]),
            Task.next_remind_at.is_not(None),
            Task.next_remind_at <= now,
        )
        .order_by(Task.next_remind_at.asc())
    )
    tasks = list((await session.execute(stmt)).scalars().all())
    if not tasks:
        return 0

    outbox = OutboxService(session)
    processed = 0
    for task in tasks:
        if task.due_at is None:
            task.next_remind_at = None
            continue

        overdue = task.due_at < now
        event_type = EventType.TASK_OVERDUE if overdue else EventType.TASK_DUE_SOON
        await outbox.enqueue(
            tenant_id=task.tenant_id,
            event_type=event_type.value,
            payload={
                "tenant_id": task.tenant_id,
                "actor_id": task.created_by,
                "task_id": task.id,
                "title": task.title,
                "due_at": task.due_at,
                "assignee_id": task.assignee_id,
                "status": task.status.value,
                "priority": task.priority.value,
                "overdue": overdue,
            },
        )
        if overdue and task.entity_type == "prescription":
            prescription = await session.get(Prescription, task.entity_id)
            if prescription is not None and str(prescription.tenant_id) == str(task.tenant_id):
                await outbox.enqueue(
                    tenant_id=task.tenant_id,
                    event_type=EventType.PRESCRIPTION_OVERDUE.value,
                    payload={
                        "tenant_id": task.tenant_id,
                        "actor_id": task.created_by,
                        "prescription_id": prescription.id,
                        "inspection_id": prescription.inspection_id,
                        "incident_id": prescription.incident_id,
                        "assignee_id": prescription.assignee_id,
                        "status": prescription.status.value,
                        "due_at": prescription.due_at,
                    },
                )
        task.next_remind_at = _next_reminder_after_send(
            task.due_at,
            reminder_days=reminder_days,
            now=now,
        )
        processed += 1

    await session.flush()
    return processed
