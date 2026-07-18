"""notify_replacement_due: horizon scan + same-day idempotency."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

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
