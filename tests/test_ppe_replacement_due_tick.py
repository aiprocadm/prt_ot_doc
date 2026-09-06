"""notify_replacement_due: horizon scan + same-day idempotency."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models.master_data import EmploymentStatus
from app.models.models import Outbox, PPEIssue, PPEItem
from app.services.ppe_notifications import notify_replacement_due

NOW = datetime.now(tz=timezone.utc)


async def _seed_issues(sessionmaker, data_factory):
    tenant = await data_factory.ensure_tenant(slug="test")
    person = await data_factory.create_person(tenant=tenant)
    async with sessionmaker() as session:
        item = PPEItem(tenant_id=tenant.id, name=f"Очки-{person.id[:8]}", default_wear_days=180)
        session.add(item)
        await session.flush()
        session.add_all(
            [
                PPEIssue(  # истекает через 10 дней → due_soon
                    tenant_id=tenant.id,
                    person_id=person.id,
                    item_id=item.id,
                    item_name=item.name,
                    quantity=1,
                    issued_at=NOW - timedelta(days=170),
                    expires_at=NOW + timedelta(days=10),
                    status="issued",
                ),
                PPEIssue(  # просрочена → overdue
                    tenant_id=tenant.id,
                    person_id=person.id,
                    item_id=item.id,
                    item_name=item.name,
                    quantity=1,
                    issued_at=NOW - timedelta(days=200),
                    expires_at=NOW - timedelta(days=20),
                    status="issued",
                ),
                PPEIssue(  # далеко → не событие
                    tenant_id=tenant.id,
                    person_id=person.id,
                    item_id=item.id,
                    item_name=item.name,
                    quantity=1,
                    issued_at=NOW,
                    expires_at=NOW + timedelta(days=300),
                    status="issued",
                ),
                PPEIssue(  # возвращена → не событие
                    tenant_id=tenant.id,
                    person_id=person.id,
                    item_id=item.id,
                    item_name=item.name,
                    quantity=1,
                    issued_at=NOW - timedelta(days=170),
                    expires_at=NOW + timedelta(days=5),
                    status="returned",
                ),
            ]
        )
        await session.commit()
    return str(tenant.id)


@pytest.mark.asyncio
async def test_notify_replacement_due_scans_and_dedups(sessionmaker, data_factory):
    tenant_id = await _seed_issues(sessionmaker, data_factory)

    async with sessionmaker() as session:
        first = await notify_replacement_due(session, tenant_id=tenant_id)
        await session.commit()
    assert first == 2  # due_soon + overdue

    async with sessionmaker() as session:
        second = await notify_replacement_due(session, tenant_id=tenant_id)
        await session.commit()
    assert second == 0  # same-day idempotent

    async with sessionmaker() as session:
        rows = (
            (await session.execute(select(Outbox).where(Outbox.event_type == "PPEReplacementDue")))
            .scalars()
            .all()
        )
        assert len(rows) == 2


@pytest.mark.asyncio
async def test_уволенному_напоминание_о_замене_сиз_не_ставится(sessionmaker, data_factory):
    """«Уволенный не в счёт» (BIZ-54-57 срез-96): просроченные СИЗ уволенного
    и удалённого человека тик пропускает — напоминание только по работающему."""
    tenant = await data_factory.ensure_tenant(slug="test")
    company = await data_factory.create_company(tenant=tenant, name="ООО Срез-96")
    here = await data_factory.create_person(tenant=tenant, company=company, last_name="Работает")
    gone = await data_factory.create_person(
        tenant=tenant,
        company=company,
        last_name="Уволен",
        employment_status=EmploymentStatus.TERMINATED,
    )
    erased = await data_factory.create_person(
        tenant=tenant, company=company, last_name="Удалён", deleted_at=NOW
    )
    async with sessionmaker() as session:
        session.add_all(
            [
                PPEIssue(
                    tenant_id=tenant.id,
                    person_id=person.id,
                    item_name="Каска",
                    quantity=1,
                    issued_at=NOW - timedelta(days=200),
                    expires_at=NOW - timedelta(days=20),
                    status="issued",
                )
                for person in (here, gone, erased)
            ]
        )
        await session.commit()

    async with sessionmaker() as session:
        created = await notify_replacement_due(session, tenant_id=str(tenant.id))
        await session.commit()
    assert created == 1

    async with sessionmaker() as session:
        rows = (
            (await session.execute(select(Outbox).where(Outbox.event_type == "PPEReplacementDue")))
            .scalars()
            .all()
        )
    assert len(rows) == 1
    assert rows[0].payload["person_id"] == here.id
