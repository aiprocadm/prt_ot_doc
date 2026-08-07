"""DB-level tests for the PPE stock ledger service (P10-06)."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select

from app.models.feature import Feature, FeatureEnablement
from app.models.ppe_registry import PPEItem, PPEStockBatch
from app.modules.ppe.stock import (
    InsufficientStockError,
    StockBatchNotFound,
    deplete_for_issue,
    record_movement,
)
from tests.utils.factories import TestDataFactory


async def _item_and_batch(session, tenant_id: str, *, qty: int):
    item = PPEItem(tenant_id=tenant_id, name="Каска")
    session.add(item)
    await session.flush()
    batch = PPEStockBatch(tenant_id=tenant_id, item_id=item.id, batch_no="B-1", quantity=qty)
    session.add(batch)
    await session.flush()
    return item, batch


@pytest.mark.asyncio
async def test_receipt_increases_balance_and_writes_journal(
    sessionmaker, data_factory: TestDataFactory
):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        _item, batch = await _item_and_batch(session, tenant.id, qty=10)

        movement = await record_movement(
            session, tenant_id=tenant.id, batch_id=batch.id, kind="receipt", quantity=5
        )
        await session.refresh(batch)

    assert batch.quantity == 15
    assert movement.quantity_delta == 5
    assert movement.kind == "receipt"
    assert movement.item_id == batch.item_id


@pytest.mark.asyncio
async def test_writeoff_decreases_balance(sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        _item, batch = await _item_and_batch(session, tenant.id, qty=10)
        movement = await record_movement(
            session, tenant_id=tenant.id, batch_id=batch.id, kind="writeoff", quantity=4
        )
        await session.refresh(batch)
    assert batch.quantity == 6
    assert movement.quantity_delta == -4


@pytest.mark.asyncio
async def test_adjustment_sets_absolute_balance(sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        _item, batch = await _item_and_batch(session, tenant.id, qty=10)
        movement = await record_movement(
            session, tenant_id=tenant.id, batch_id=batch.id, kind="adjustment", quantity=7
        )
        await session.refresh(batch)
    assert batch.quantity == 7
    assert movement.quantity_delta == -3  # 7 - 10


@pytest.mark.asyncio
async def test_writeoff_below_zero_raises(sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        _item, batch = await _item_and_batch(session, tenant.id, qty=3)
        with pytest.raises(InsufficientStockError):
            await record_movement(
                session, tenant_id=tenant.id, batch_id=batch.id, kind="writeoff", quantity=5
            )


@pytest.mark.asyncio
async def test_unknown_batch_raises(sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        with pytest.raises(StockBatchNotFound):
            await record_movement(
                session, tenant_id=tenant.id, batch_id="nope", kind="receipt", quantity=1
            )


@pytest.mark.asyncio
async def test_deplete_fifo_spans_batches_oldest_first(sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        item = PPEItem(tenant_id=tenant.id, name="Перчатки")
        session.add(item)
        await session.flush()
        old = PPEStockBatch(
            tenant_id=tenant.id,
            item_id=item.id,
            batch_no="OLD",
            quantity=3,
            received_at=date(2026, 1, 1),
        )
        new = PPEStockBatch(
            tenant_id=tenant.id,
            item_id=item.id,
            batch_no="NEW",
            quantity=10,
            received_at=date(2026, 6, 1),
        )
        session.add_all([old, new])
        await session.flush()

        movements = await deplete_for_issue(
            session, tenant_id=tenant.id, item_id=item.id, quantity=7, ref_id="issue-1"
        )
        await session.refresh(old)
        await session.refresh(new)

    assert old.quantity == 0  # oldest drained first
    assert new.quantity == 6  # remainder from newer
    assert [m.quantity_delta for m in movements] == [-3, -4]
    assert all(
        m.kind == "issue" and m.ref_type == "ppe_issue" and m.ref_id == "issue-1" for m in movements
    )


@pytest.mark.asyncio
async def test_deplete_explicit_batch_only(sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        item = PPEItem(tenant_id=tenant.id, name="Каска")
        session.add(item)
        await session.flush()
        b1 = PPEStockBatch(
            tenant_id=tenant.id,
            item_id=item.id,
            batch_no="B-1",
            quantity=5,
            received_at=date(2026, 1, 1),
        )
        b2 = PPEStockBatch(
            tenant_id=tenant.id,
            item_id=item.id,
            batch_no="B-2",
            quantity=5,
            received_at=date(2026, 2, 1),
        )
        session.add_all([b1, b2])
        await session.flush()

        movements = await deplete_for_issue(
            session,
            tenant_id=tenant.id,
            item_id=item.id,
            quantity=2,
            batch_id=b2.id,
            ref_id="issue-2",
        )
        await session.refresh(b1)
        await session.refresh(b2)

    assert b1.quantity == 5  # untouched: explicit override picked b2
    assert b2.quantity == 3
    assert len(movements) == 1 and movements[0].batch_id == b2.id


@pytest.mark.asyncio
async def test_deplete_insufficient_raises(sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        item = PPEItem(tenant_id=tenant.id, name="Каска")
        session.add(item)
        await session.flush()
        session.add(PPEStockBatch(tenant_id=tenant.id, item_id=item.id, batch_no="B", quantity=2))
        await session.flush()
        with pytest.raises(InsufficientStockError):
            await deplete_for_issue(
                session, tenant_id=tenant.id, item_id=item.id, quantity=5, ref_id="i"
            )


@pytest.mark.asyncio
async def test_deplete_noop_when_item_has_no_batches(sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        item = PPEItem(tenant_id=tenant.id, name="Каска")
        session.add(item)
        await session.flush()
        movements = await deplete_for_issue(
            session, tenant_id=tenant.id, item_id=item.id, quantity=3, ref_id="i"
        )
    assert movements == []


@pytest.mark.asyncio
async def test_deplete_noop_when_flag_disabled(sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        # explicit opt-out
        feature = Feature(code="warehouse", title="Warehouse")
        session.add(feature)
        await session.flush()
        session.add(FeatureEnablement(tenant_id=tenant.id, feature_id=feature.id, on=False))
        item = PPEItem(tenant_id=tenant.id, name="Каска")
        session.add(item)
        await session.flush()
        session.add(PPEStockBatch(tenant_id=tenant.id, item_id=item.id, batch_no="B", quantity=10))
        await session.flush()
        movements = await deplete_for_issue(
            session, tenant_id=tenant.id, item_id=item.id, quantity=3, ref_id="i"
        )
        batch = (
            await session.execute(select(PPEStockBatch).where(PPEStockBatch.item_id == item.id))
        ).scalar_one()
    assert movements == []
    assert batch.quantity == 10  # untouched when flag off


@pytest.mark.asyncio
async def test_record_movement_persists_ref_type_and_id(
    sessionmaker, data_factory: TestDataFactory
):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        _item, batch = await _item_and_batch(session, tenant.id, qty=10)

        movement = await record_movement(
            session,
            tenant_id=tenant.id,
            batch_id=batch.id,
            kind="adjustment",
            quantity=7,
            reason="inventory abc",
            ref_type="ppe_inventory_count",
            ref_id="count-123",
        )

    assert movement.ref_type == "ppe_inventory_count"
    assert movement.ref_id == "count-123"
    assert movement.quantity_delta == -3  # 10 -> 7 absolute
