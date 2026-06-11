"""ppe.expiry.tick: drives notify_replacement_due across active tenants."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models.models import Outbox, PPEIssue, PPEItem

NOW = datetime.now(tz=timezone.utc)


@pytest.mark.asyncio
async def test_ppe_expiry_tick_enqueues(sessionmaker, data_factory):
    from app.tasks._core import _ppe_expiry_tick

    tenant = await data_factory.ensure_tenant(slug="test")
    person = await data_factory.create_person(tenant=tenant)
    async with sessionmaker() as session:
        item = PPEItem(tenant_id=tenant.id, name=f"Очки-{person.id[:8]}", default_wear_days=180)
        session.add(item)
        await session.flush()
        session.add(PPEIssue(  # истекает через 10 дней → due_soon
            tenant_id=tenant.id, person_id=person.id, item_id=item.id,
            item_name=item.name, quantity=1, issued_at=NOW - timedelta(days=170),
            expires_at=NOW + timedelta(days=10), status="issued",
        ))
        await session.commit()

    total = await _ppe_expiry_tick()
    assert total >= 1

    async with sessionmaker() as session:
        rows = (await session.execute(
            select(Outbox).where(Outbox.event_type == "PPEReplacementDue")
        )).scalars().all()
        assert len(rows) >= 1
