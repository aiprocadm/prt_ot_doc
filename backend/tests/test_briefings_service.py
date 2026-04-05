from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import Column, String, Table
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.session import TenantBase
from app.models.models import BriefingEntry, BriefingJournal, BriefingTemplate
from app.modules.briefings.services import BriefingEntryService


@pytest.fixture()
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    if "tenant" not in TenantBase.metadata.tables:
        Table("tenant", TenantBase.metadata, Column("id", String(36), primary_key=True))
    async with engine.begin() as conn:
        await conn.run_sync(TenantBase.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_briefing_sign_is_idempotent_and_complete_sets_valid_until(db_session) -> None:
    tenant_id = "tenant-1"
    template = BriefingTemplate(tenant_id=tenant_id, code="bt-1", title="Intro", briefing_type="introductory", status="active", validity_days=30)
    journal = BriefingJournal(tenant_id=tenant_id, code="bj-1", title="Main", journal_type="ot", status="active")
    db_session.add_all([template, journal])
    await db_session.flush()
    entry = BriefingEntry(
        tenant_id=tenant_id,
        briefing_journal_id=journal.id,
        briefing_template_id=template.id,
        briefing_type="introductory",
        briefing_date=datetime(2026, 3, 1, tzinfo=timezone.utc),
        status="assigned",
    )
    db_session.add(entry)
    await db_session.flush()

    service = BriefingEntryService()
    first = await service.sign(db_session, entry, "employee", "user-1")
    second = await service.sign(db_session, entry, "employee", "user-1")
    assert first.id == second.id

    await service.sign(db_session, entry, "instructor", "user-2")
    completed = await service.complete(db_session, entry)
    assert completed.status == "completed"
    assert completed.valid_until == datetime(2026, 3, 31, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_briefing_overdue_notifications_enqueue_task_overdue(db_session) -> None:
    tenant_id = "tenant-1"
    journal = BriefingJournal(tenant_id=tenant_id, code="bj-1", title="Main", journal_type="ot", status="active")
    db_session.add(journal)
    await db_session.flush()
    overdue = BriefingEntry(
        tenant_id=tenant_id,
        briefing_journal_id=journal.id,
        briefing_type="periodic",
        briefing_date=datetime.now(timezone.utc) - timedelta(days=90),
        valid_until=datetime.now(timezone.utc) - timedelta(days=1),
        person_id="person-1",
        status="assigned",
    )
    db_session.add(overdue)
    await db_session.flush()

    enqueue = AsyncMock()
    with patch("app.modules.briefings.services.OutboxService.enqueue", enqueue):
        items = await BriefingEntryService().notify_overdue(db_session, tenant_id=tenant_id, actor_id="actor-1")

    assert [item.id for item in items] == [overdue.id]
    enqueue.assert_awaited_once()
    call = enqueue.await_args.kwargs
    assert call["event_type"] == "TaskOverdue"
    assert call["payload"]["task_id"] == overdue.id
    assert call["payload"]["assignee_id"] == "person-1"


@pytest.mark.asyncio
async def test_briefing_complete_skips_validity_when_template_other_tenant(db_session) -> None:
    tenant_entry = "tenant-entry"
    tenant_tpl = "tenant-tpl"
    template = BriefingTemplate(
        tenant_id=tenant_tpl,
        code="bt-cross",
        title="Cross tenant tpl",
        briefing_type="introductory",
        status="active",
        validity_days=30,
    )
    journal = BriefingJournal(
        tenant_id=tenant_entry,
        code="bj-cross",
        title="Main",
        journal_type="ot",
        status="active",
    )
    db_session.add_all([template, journal])
    await db_session.flush()
    entry = BriefingEntry(
        tenant_id=tenant_entry,
        briefing_journal_id=journal.id,
        briefing_template_id=template.id,
        briefing_type="introductory",
        briefing_date=datetime(2026, 3, 1, tzinfo=timezone.utc),
        status="assigned",
    )
    db_session.add(entry)
    await db_session.flush()

    service = BriefingEntryService()
    await service.sign(db_session, entry, "employee", "user-1")
    await service.sign(db_session, entry, "instructor", "user-2")
    completed = await service.complete(db_session, entry)
    assert completed.status == "completed"
    assert completed.valid_until is None
