from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models.models import (
    Inspection,
    InspectionStatus,
    InspectionType,
    Outbox,
    Prescription,
    PrescriptionStatus,
)
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

        outbox = (
            (await session.execute(select(Outbox).where(Outbox.event_type == "TaskDueSoon")))
            .scalars()
            .all()
        )
        assert outbox


@pytest.mark.anyio
async def test_task_reminder_overdue_and_schedule(sessionmaker, data_factory):
    now = datetime(2025, 1, 1, tzinfo=timezone.utc)
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        tenant.settings = {"obligations": {"reminder_days": [10, 5]}}
        session.info["tenant_id"] = tenant.id
        session.info["tenant_slug"] = tenant.slug
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
            (await session.execute(select(Outbox).where(Outbox.event_type == "TaskOverdue")))
            .scalars()
            .all()
        )
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
        session.info["tenant_id"] = tenant.id
        session.info["tenant_slug"] = tenant.slug
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


@pytest.mark.anyio
async def test_task_reminder_uses_canonical_tenant_id_for_settings(sessionmaker, data_factory):
    now = datetime(2025, 1, 1, tzinfo=timezone.utc)
    due_at = now + timedelta(days=6)
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        tenant.settings = {"obligations": {"reminder_days": [9, 4]}}
        session.info["tenant_id"] = tenant.id
        task = Task(
            tenant_id=tenant.id,
            title="Canonical task",
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
        assert task.next_remind_at == (due_at - timedelta(days=4)).replace(tzinfo=None)


@pytest.mark.anyio
async def test_prescription_overdue_emits_dedicated_outbox_event(sessionmaker, data_factory):
    now = datetime(2025, 1, 1, tzinfo=timezone.utc)
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        inspection = Inspection(
            tenant_id=tenant.id,
            company_id="company-1",
            site_id=None,
            inspection_type=InspectionType.INTERNAL,
            responsible_id=None,
            authority="RPN",
            purpose="Check",
            status=InspectionStatus.PLANNED,
            scheduled_at=now,
        )
        session.add(inspection)
        await session.flush()
        prescription = Prescription(
            tenant_id=tenant.id,
            inspection_id=inspection.id,
            incident_id=None,
            description="Close finding",
            due_at=(now - timedelta(days=2)).date(),
            status=PrescriptionStatus.OPEN,
            assignee_id=None,
        )
        session.add(prescription)
        await session.flush()
        task = Task(
            tenant_id=tenant.id,
            title="Prescription overdue",
            entity_type="prescription",
            entity_id=prescription.id,
            due_at=now - timedelta(days=1),
            status=TaskStatus.OPEN,
            priority=TaskPriority.HIGH,
            reminder_channel=TaskReminderChannel.IN_APP,
            next_remind_at=now - timedelta(minutes=1),
        )
        session.add(task)
        await session.commit()

        processed = await process_task_reminders(session, now=now)
        assert processed == 1

        outbox = (
            (
                await session.execute(
                    select(Outbox).where(Outbox.event_type == "PrescriptionOverdue")
                )
            )
            .scalars()
            .all()
        )
        assert len(outbox) == 1
        assert outbox[0].payload["prescription_id"] == prescription.id
