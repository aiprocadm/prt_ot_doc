"""ORM round-trip for PPESafetyBudget + PPEStockBatch.unit_cost (P10-06)."""
from __future__ import annotations

from datetime import date

import pytest

from app.models.models import PPEItem, PPESafetyBudget
from app.models.ppe_registry import PPEStockBatch
from tests.utils.factories import TestDataFactory


@pytest.mark.asyncio
async def test_budget_roundtrip(sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        b = PPESafetyBudget(
            tenant_id=tenant.id,
            name="Бюджет 2026",
            period_start=date(2026, 1, 1),
            period_end=date(2026, 12, 31),
            planned_amount=100000,
            notes="годовой",
        )
        session.add(b)
        await session.flush()
        await session.refresh(b)
        assert b.name == "Бюджет 2026"
        assert float(b.planned_amount) == 100000.0
        assert b.deleted_at is None


@pytest.mark.asyncio
async def test_batch_unit_cost_nullable(sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        item = PPEItem(tenant_id=tenant.id, name="Каска")
        session.add(item)
        await session.flush()
        priced = PPEStockBatch(
            tenant_id=tenant.id, item_id=item.id, batch_no="B1", quantity=0, unit_cost=250
        )
        unpriced = PPEStockBatch(
            tenant_id=tenant.id, item_id=item.id, batch_no="B2", quantity=0
        )
        session.add_all([priced, unpriced])
        await session.flush()
        await session.refresh(priced)
        await session.refresh(unpriced)
        assert float(priced.unit_cost) == 250.0
        assert unpriced.unit_cost is None
