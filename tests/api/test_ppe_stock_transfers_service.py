"""DB-level tests for the PPE stock transfer service (P10-06)."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models.ppe_registry import PPEItem, PPEStockBatch
from app.modules.ppe.stock import (
    InsufficientStockError,
    StockBatchNotFound,
    transfer_stock,
)
from tests.utils.factories import TestDataFactory


async def _item_and_batch(session, tenant_id, *, qty, location="A", no="B-1"):
    item = PPEItem(tenant_id=tenant_id, name="Каска")
    session.add(item)
    await session.flush()
    batch = PPEStockBatch(
        tenant_id=tenant_id, item_id=item.id, batch_no=no, quantity=qty, location=location
    )
    session.add(batch)
    await session.flush()
    return item, batch


async def _on_hand(session, tenant_id, item_id):
    rows = (
        (
            await session.execute(
                select(PPEStockBatch.quantity).where(
                    PPEStockBatch.tenant_id == tenant_id,
                    PPEStockBatch.item_id == item_id,
                    PPEStockBatch.deleted_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    return sum(int(q) for q in rows)


@pytest.mark.asyncio
async def test_partial_transfer_creates_dest_and_keeps_item_on_hand(
    sessionmaker, data_factory: TestDataFactory
):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        item, source = await _item_and_batch(session, tenant.id, qty=10, location="A")

        before = await _on_hand(session, tenant.id, item.id)
        result = await transfer_stock(
            session,
            tenant_id=tenant.id,
            source_batch_id=source.id,
            to_location="B",
            quantity=3,
        )
        await session.refresh(source)
        after = await _on_hand(session, tenant.id, item.id)

        dest = (
            await session.execute(
                select(PPEStockBatch).where(PPEStockBatch.id == result.dest_batch_id)
            )
        ).scalar_one()

    assert source.quantity == 7
    assert dest.quantity == 3
    assert dest.location == "B"
    assert dest.batch_no == source.batch_no
    assert dest.id != source.id
    assert before == after == 10
    assert result.out_movement.kind == "transfer"
    assert result.in_movement.kind == "transfer"
    assert result.out_movement.quantity_delta == -3
    assert result.in_movement.quantity_delta == 3
    assert result.out_movement.ref_id == result.in_movement.ref_id == result.ref_id
    assert result.out_movement.ref_type == "ppe_transfer"
    assert result.from_location == "A"
    assert result.to_location == "B"
    assert result.batch_no == source.batch_no


@pytest.mark.asyncio
async def test_second_transfer_merges_into_existing_dest_batch(
    sessionmaker, data_factory: TestDataFactory
):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        item, source = await _item_and_batch(session, tenant.id, qty=10, location="A")

        first = await transfer_stock(
            session,
            tenant_id=tenant.id,
            source_batch_id=source.id,
            to_location="B",
            quantity=3,
        )
        second = await transfer_stock(
            session,
            tenant_id=tenant.id,
            source_batch_id=source.id,
            to_location="B",
            quantity=2,
        )
        await session.refresh(source)

        assert first.dest_batch_id == second.dest_batch_id
        dest_batches = (
            (
                await session.execute(
                    select(PPEStockBatch).where(
                        PPEStockBatch.tenant_id == tenant.id,
                        PPEStockBatch.item_id == item.id,
                        PPEStockBatch.location == "B",
                        PPEStockBatch.deleted_at.is_(None),
                    )
                )
            )
            .scalars()
            .all()
        )

    assert len(dest_batches) == 1
    assert dest_batches[0].quantity == 5
    assert source.quantity == 5


@pytest.mark.asyncio
async def test_full_transfer_empties_source(sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        item, source = await _item_and_batch(session, tenant.id, qty=6, location="A")
        result = await transfer_stock(
            session,
            tenant_id=tenant.id,
            source_batch_id=source.id,
            to_location="B",
            quantity=6,
        )
        await session.refresh(source)
        dest = (
            await session.execute(
                select(PPEStockBatch).where(PPEStockBatch.id == result.dest_batch_id)
            )
        ).scalar_one()
    assert source.quantity == 0
    assert dest.quantity == 6


@pytest.mark.asyncio
async def test_transfer_more_than_on_hand_raises(sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        _item, source = await _item_and_batch(session, tenant.id, qty=2, location="A")
        with pytest.raises(InsufficientStockError):
            await transfer_stock(
                session,
                tenant_id=tenant.id,
                source_batch_id=source.id,
                to_location="B",
                quantity=5,
            )


@pytest.mark.asyncio
async def test_transfer_to_same_location_raises(sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        _item, source = await _item_and_batch(session, tenant.id, qty=5, location="A")
        with pytest.raises(ValueError):
            await transfer_stock(
                session,
                tenant_id=tenant.id,
                source_batch_id=source.id,
                to_location="A",
                quantity=1,
            )


@pytest.mark.asyncio
async def test_transfer_empty_location_raises(sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        _item, source = await _item_and_batch(session, tenant.id, qty=5, location="A")
        with pytest.raises(ValueError):
            await transfer_stock(
                session,
                tenant_id=tenant.id,
                source_batch_id=source.id,
                to_location="   ",
                quantity=1,
            )


@pytest.mark.asyncio
async def test_transfer_unknown_source_raises(sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        with pytest.raises(StockBatchNotFound):
            await transfer_stock(
                session,
                tenant_id=tenant.id,
                source_batch_id="nope",
                to_location="B",
                quantity=1,
            )


@pytest.mark.asyncio
async def test_transfer_copies_unit_cost_to_dest_batch(sessionmaker, data_factory: TestDataFactory):
    """The auto-created dest batch inherits the source's per-unit cost (provenance),
    so a later receipt onto it is priced instead of silently dropped from the safety
    budget's ``actual_total`` as an unpriced receipt."""
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        item = PPEItem(tenant_id=tenant.id, name="Каска")
        session.add(item)
        await session.flush()
        source = PPEStockBatch(
            tenant_id=tenant.id,
            item_id=item.id,
            batch_no="B-1",
            quantity=8,
            location="A",
            unit_cost=125,
        )
        session.add(source)
        await session.flush()

        result = await transfer_stock(
            session,
            tenant_id=tenant.id,
            source_batch_id=source.id,
            to_location="B",
            quantity=3,
        )
        dest = (
            await session.execute(
                select(PPEStockBatch).where(PPEStockBatch.id == result.dest_batch_id)
            )
        ).scalar_one()

    assert dest.unit_cost is not None
    assert float(dest.unit_cost) == 125.0
