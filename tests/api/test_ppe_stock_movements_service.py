"""DB-level tests for the PPE stock ledger service (P10-06)."""
from __future__ import annotations

import pytest

from app.models.ppe_registry import PPEItem, PPEStockBatch
from app.modules.ppe.stock import (
    InsufficientStockError,
    StockBatchNotFound,
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
async def test_receipt_increases_balance_and_writes_journal(sessionmaker, data_factory: TestDataFactory):
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
