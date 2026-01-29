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
