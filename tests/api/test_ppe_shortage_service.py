"""compute_shortages aggregation over batches + issue movements (P10-06)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.models.ppe import PPEItem, PPEStockBatch, PPEStockMovement
from app.modules.ppe.stock import KIND_ISSUE, KIND_RECEIPT, compute_shortages
from tests.utils.factories import TestDataFactory

NOW = datetime(2026, 7, 3, tzinfo=timezone.utc)


async def _mk_item(session, tenant_id, *, name, min_stock):
    item = PPEItem(tenant_id=tenant_id, name=name, min_stock=min_stock)
    session.add(item)
    await session.flush()
    return item


async def _mk_batch(session, tenant_id, item_id, qty):
    batch_no = f"B-{uuid4().hex[:8]}"
    batch = PPEStockBatch(tenant_id=tenant_id, item_id=item_id, batch_no=batch_no, quantity=qty)
    session.add(batch)
    await session.flush()
    return batch


async def _mk_issue(session, tenant_id, item_id, batch_id, qty, occurred_at):
    session.add(
        PPEStockMovement(
            tenant_id=tenant_id,
            item_id=item_id,
            batch_id=batch_id,
            kind=KIND_ISSUE,
            quantity_delta=-qty,
            occurred_at=occurred_at,
        )
    )
    await session.flush()


@pytest.mark.asyncio
async def test_only_items_with_threshold_are_watched(sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        await _mk_item(session, tenant.id, name="watched", min_stock=10)
        await _mk_item(session, tenant.id, name="ignored", min_stock=0)
        await session.commit()
    async with sessionmaker() as session:
        rows = await compute_shortages(session, tenant.id, now=NOW)
    names = {r.item_name for r in rows}
    assert names == {"watched"}


@pytest.mark.asyncio
async def test_on_hand_sums_batches_and_flags_below(sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        item = await _mk_item(session, tenant.id, name="caps", min_stock=20)
        await _mk_batch(session, tenant.id, item.id, 5)
        await _mk_batch(session, tenant.id, item.id, 4)
        await session.commit()
    async with sessionmaker() as session:
        rows = await compute_shortages(session, tenant.id, now=NOW)
    assert len(rows) == 1
    assert rows[0].on_hand == 9
    assert rows[0].below_threshold is True
    assert rows[0].deficit == 11


@pytest.mark.asyncio
async def test_avg_daily_uses_only_issues_in_window(sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        item = await _mk_item(session, tenant.id, name="gloves", min_stock=1)
        batch = await _mk_batch(session, tenant.id, item.id, 90)
        await _mk_issue(session, tenant.id, item.id, batch.id, 90, NOW - timedelta(days=10))
        await _mk_issue(session, tenant.id, item.id, batch.id, 999, NOW - timedelta(days=200))
        session.add(
            PPEStockMovement(
                tenant_id=tenant.id,
                item_id=item.id,
                batch_id=batch.id,
                kind=KIND_RECEIPT,
                quantity_delta=500,
                occurred_at=NOW - timedelta(days=5),
            )
        )
        await session.commit()
    async with sessionmaker() as session:
        rows = await compute_shortages(session, tenant.id, now=NOW, window_days=90)
    assert rows[0].avg_daily_consumption == pytest.approx(1.0)
    assert rows[0].days_to_depletion == pytest.approx(90.0)


@pytest.mark.asyncio
async def test_only_below_filters_out_healthy(sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        low = await _mk_item(session, tenant.id, name="low", min_stock=10)
        await _mk_batch(session, tenant.id, low.id, 1)
        ok = await _mk_item(session, tenant.id, name="ok", min_stock=10)
        await _mk_batch(session, tenant.id, ok.id, 50)
        await session.commit()
    async with sessionmaker() as session:
        rows = await compute_shortages(session, tenant.id, now=NOW, only_below=True)
    assert [r.item_name for r in rows] == ["low"]
