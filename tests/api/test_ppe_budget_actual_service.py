"""Procurement actual computation for the safety budget (P10-06)."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from app.models.models import PPEItem, PPEItemCategory
from app.models.ppe_registry import PPEStockBatch, PPEStockMovement
from app.modules.ppe.budget import compute_budget_actual
from tests.utils.factories import TestDataFactory

PS, PE = date(2026, 1, 1), date(2026, 12, 31)


async def _item(session, tenant_id, *, name, category=PPEItemCategory.HEAD):
    it = PPEItem(tenant_id=tenant_id, name=name, category=category)
    session.add(it)
    await session.flush()
    return it


async def _batch(session, tenant_id, item_id, *, unit_cost, no="B"):
    b = PPEStockBatch(
        tenant_id=tenant_id, item_id=item_id, batch_no=no, quantity=0, unit_cost=unit_cost
    )
    session.add(b)
    await session.flush()
    return b


async def _movement(session, tenant_id, item_id, batch_id, *, kind, delta, when):
    m = PPEStockMovement(
        tenant_id=tenant_id,
        item_id=item_id,
        batch_id=batch_id,
        kind=kind,
        quantity_delta=delta,
        occurred_at=when,
    )
    session.add(m)
    await session.flush()
    return m


@pytest.mark.asyncio
async def test_sums_receipts_in_period(sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        t = await data_factory.ensure_tenant(session=session)
        it = await _item(session, t.id, name="Каска")
        b = await _batch(session, t.id, it.id, unit_cost=100)
        await _movement(
            session,
            t.id,
            it.id,
            b.id,
            kind="receipt",
            delta=3,
            when=datetime(2026, 6, 1, tzinfo=timezone.utc),
        )
        await _movement(
            session,
            t.id,
            it.id,
            b.id,
            kind="receipt",
            delta=5,
            when=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )
        actual = await compute_budget_actual(session, t.id, PS, PE)
        assert actual.actual_total == 300.0
        assert actual.priced_receipt_count == 1
        assert actual.unpriced_receipt_count == 0


@pytest.mark.asyncio
async def test_only_receipt_kind_counts(sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        t = await data_factory.ensure_tenant(session=session)
        it = await _item(session, t.id, name="Каска")
        b = await _batch(session, t.id, it.id, unit_cost=100)
        when = datetime(2026, 6, 1, tzinfo=timezone.utc)
        await _movement(session, t.id, it.id, b.id, kind="receipt", delta=2, when=when)
        for kind, delta in [("issue", -1), ("writeoff", -1), ("adjustment", 4), ("transfer", -1)]:
            await _movement(session, t.id, it.id, b.id, kind=kind, delta=delta, when=when)
        actual = await compute_budget_actual(session, t.id, PS, PE)
        assert actual.actual_total == 200.0


@pytest.mark.asyncio
async def test_unpriced_excluded_but_counted(sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        t = await data_factory.ensure_tenant(session=session)
        it = await _item(session, t.id, name="Каска")
        priced = await _batch(session, t.id, it.id, unit_cost=100, no="P")
        unpriced = await _batch(session, t.id, it.id, unit_cost=None, no="U")
        when = datetime(2026, 6, 1, tzinfo=timezone.utc)
        await _movement(session, t.id, it.id, priced.id, kind="receipt", delta=2, when=when)
        await _movement(session, t.id, it.id, unpriced.id, kind="receipt", delta=9, when=when)
        actual = await compute_budget_actual(session, t.id, PS, PE)
        assert actual.actual_total == 200.0
        assert actual.priced_receipt_count == 1
        assert actual.unpriced_receipt_count == 1


@pytest.mark.asyncio
async def test_category_breakdown(sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        t = await data_factory.ensure_tenant(session=session)
        head = await _item(session, t.id, name="Каска", category=PPEItemCategory.HEAD)
        hands = await _item(session, t.id, name="Перчатки", category=PPEItemCategory.HANDS)
        bh = await _batch(session, t.id, head.id, unit_cost=100, no="H")
        bg = await _batch(session, t.id, hands.id, unit_cost=10, no="G")
        when = datetime(2026, 6, 1, tzinfo=timezone.utc)
        await _movement(session, t.id, head.id, bh.id, kind="receipt", delta=1, when=when)
        await _movement(session, t.id, hands.id, bg.id, kind="receipt", delta=2, when=when)
        actual = await compute_budget_actual(session, t.id, PS, PE)
        assert actual.actual_total == 120.0
        cats = {c.category: c.amount for c in actual.by_category}
        assert cats == {"head": 100.0, "hands": 20.0}
        assert actual.by_category[0].category == "head"  # sorted by amount desc
