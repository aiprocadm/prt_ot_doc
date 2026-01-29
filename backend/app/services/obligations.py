"""Task orchestration for deadlines and obligations."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.obligations import Task, TaskPriority, TaskReminderChannel, TaskStatus
from app.models.models import TrainingCourse, TrainingPlan
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


def _next_reminder(due_at: datetime | None, *, lead_days: int = 2) -> datetime | None:
    if due_at is None:
        return None
    reminder = due_at - timedelta(days=lead_days)
    now = datetime.now(timezone.utc)
    return reminder if reminder > now else due_at


async def create_training_task(
    session: AsyncSession,
    *,
    tenant_id: str,
    plan: TrainingPlan,
    course: TrainingCourse,
    actor_id: str | None,
) -> Task:
    due_at = _due_datetime(plan.due_date)
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
        next_remind_at=_next_reminder(due_at),
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
        next_remind_at=_next_reminder(due_at),
    )
    session.add(task)
    await session.flush()
    return task


async def process_task_reminders(
    session: AsyncSession,
    *,
    now: datetime | None = None,
    lead_days: int = 2,
) -> int:
    now = now or datetime.now(timezone.utc)
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
        task.next_remind_at = now + timedelta(days=1)
        processed += 1

    await session.flush()
    return processed
