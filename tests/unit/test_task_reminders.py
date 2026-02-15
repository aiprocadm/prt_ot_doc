from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models.models import Outbox
from app.models.obligations import Task, TaskPriority, TaskReminderChannel, TaskStatus
from app.services.obligations import process_task_reminders


@pytest.mark.anyio
async def test_task_reminder_emits_outbox(sessionmaker, data_factory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        task = Task(
            tenant_id=tenant.id,
            title="Due soon task",
            due_at=datetime.now(timezone.utc) + timedelta(days=1),
            status=TaskStatus.OPEN,
            priority=TaskPriority.MEDIUM,
            reminder_channel=TaskReminderChannel.IN_APP,
            next_remind_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )
        session.add(task)
        await session.commit()

        processed = await process_task_reminders(session)
        assert processed == 1

        outbox = (await session.execute(select(Outbox).where(Outbox.event_type == "TaskDueSoon"))).scalars().all()
        assert outbox


@pytest.mark.anyio
async def test_task_reminder_overdue_and_schedule(sessionmaker, data_factory):
    now = datetime(2025, 1, 1, tzinfo=timezone.utc)
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        tenant.settings = {"obligations": {"reminder_days": [10, 5]}}
        session.info["tenant"] = tenant.slug
        task = Task(
            tenant_id=tenant.id,
            title="Overdue task",
            due_at=now - timedelta(days=1),
            status=TaskStatus.OPEN,
            priority=TaskPriority.MEDIUM,
            reminder_channel=TaskReminderChannel.IN_APP,
            next_remind_at=now - timedelta(minutes=1),
        )
        session.add(task)
        await session.commit()

        processed = await process_task_reminders(session, now=now)
        assert processed == 1

        outbox = (
            await session.execute(select(Outbox).where(Outbox.event_type == "TaskOverdue"))
        ).scalars().all()
        assert outbox
        await session.refresh(task)
        assert task.next_remind_at == (now + timedelta(days=1)).replace(tzinfo=None)


@pytest.mark.anyio
async def test_task_reminder_uses_tenant_windows(sessionmaker, data_factory):
    now = datetime(2025, 1, 1, tzinfo=timezone.utc)
    due_at = now + timedelta(days=6)
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        tenant.settings = {"obligations": {"reminder_days": [10, 5]}}
        session.info["tenant"] = tenant.slug
        task = Task(
            tenant_id=tenant.id,
            title="Upcoming task",
            due_at=due_at,
            status=TaskStatus.OPEN,
            priority=TaskPriority.MEDIUM,
            reminder_channel=TaskReminderChannel.IN_APP,
            next_remind_at=now - timedelta(minutes=5),
        )
        session.add(task)
        await session.commit()

        processed = await process_task_reminders(session, now=now)
        assert processed == 1
        await session.refresh(task)
        assert task.next_remind_at == (due_at - timedelta(days=5)).replace(tzinfo=None)
