"""Service tests for the PPE inventory-count workflow (P10-06)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.models.ppe import PPEItem, PPEStockBatch
from app.modules.ppe.inventory import create_count, get_count_detail
from tests.utils.factories import TestDataFactory

NOW = datetime(2026, 7, 3, tzinfo=timezone.utc)


async def _item(session, tenant_id, *, name):
    item = PPEItem(tenant_id=tenant_id, name=name)
    session.add(item)
    await session.flush()
    return item


async def _batch(session, tenant_id, item_id, *, batch_no, qty, location=None):
    batch = PPEStockBatch(
        tenant_id=tenant_id,
        item_id=item_id,
        batch_no=batch_no,
        quantity=qty,
        location=location,
    )
    session.add(batch)
    await session.flush()
    return batch


@pytest.mark.asyncio
async def test_create_count_seeds_line_per_batch_with_snapshot(
    sessionmaker, data_factory: TestDataFactory
):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        item = await _item(session, tenant.id, name="Каска")
        await _batch(session, tenant.id, item.id, batch_no="B-1", qty=10)
        await _batch(session, tenant.id, item.id, batch_no="B-2", qty=4)

        count = await create_count(session, tenant_id=tenant.id, note="июль")
        detail = await get_count_detail(session, tenant.id, count.id)

    assert count.status == "draft"
    assert detail.line_count == 2
    assert {line.system_qty for line in detail.lines} == {10, 4}
    assert all(line.counted_qty is None for line in detail.lines)
    assert all(line.delta is None for line in detail.lines)
    assert {line.on_hand for line in detail.lines} == {10, 4}


@pytest.mark.asyncio
async def test_create_count_scope_filters_by_item_and_location(
    sessionmaker, data_factory: TestDataFactory
):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        item_a = await _item(session, tenant.id, name="A")
        item_b = await _item(session, tenant.id, name="B")
        await _batch(session, tenant.id, item_a.id, batch_no="A-1", qty=5, location="Склад-1")
        await _batch(session, tenant.id, item_a.id, batch_no="A-2", qty=5, location="Склад-2")
        await _batch(session, tenant.id, item_b.id, batch_no="B-1", qty=5, location="Склад-1")

        by_item = await create_count(session, tenant_id=tenant.id, scope_item_id=item_a.id)
        by_loc = await create_count(session, tenant_id=tenant.id, scope_location="Склад-1")
        d_item = await get_count_detail(session, tenant.id, by_item.id)
        d_loc = await get_count_detail(session, tenant.id, by_loc.id)

    assert d_item.line_count == 2  # both item_a batches
    assert d_loc.line_count == 2  # both Склад-1 batches (across items)


@pytest.mark.asyncio
async def test_create_count_no_matching_batches_is_empty(
    sessionmaker, data_factory: TestDataFactory
):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        count = await create_count(session, tenant_id=tenant.id, scope_location="Нет-такой")
        detail = await get_count_detail(session, tenant.id, count.id)

    assert detail.line_count == 0
    assert detail.lines == []


@pytest.mark.asyncio
async def test_detail_counted_line_with_soft_deleted_batch_has_none_delta(
    sessionmaker, data_factory: TestDataFactory
):
    from sqlalchemy import select

    from app.models.ppe import PPEInventoryCountLine

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        item = await _item(session, tenant.id, name="Каска")
        batch = await _batch(session, tenant.id, item.id, batch_no="B-1", qty=10)
        count = await create_count(session, tenant_id=tenant.id)
        detail = await get_count_detail(session, tenant.id, count.id)
        line_id = detail.lines[0].id
        # physical count recorded, then the batch is soft-deleted afterwards
        orm_line = (
            await session.execute(
                select(PPEInventoryCountLine).where(PPEInventoryCountLine.id == line_id)
            )
        ).scalar_one()
        orm_line.counted_qty = 8
        batch.deleted_at = NOW
        await session.flush()
        after = await get_count_detail(session, tenant.id, count.id)

    assert after.line_count == 1
    assert after.lines[0].on_hand == 0
    assert after.lines[0].counted_qty == 8
    assert after.lines[0].delta is None
    assert after.counted_count == 1
    assert after.diff_count == 0


@pytest.mark.asyncio
async def test_set_line_counts_updates_only_named_lines(
    sessionmaker, data_factory: TestDataFactory
):
    from app.modules.ppe.inventory import set_line_counts

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        item = await _item(session, tenant.id, name="Каска")
        await _batch(session, tenant.id, item.id, batch_no="B-1", qty=10)
        await _batch(session, tenant.id, item.id, batch_no="B-2", qty=4)
        count = await create_count(session, tenant_id=tenant.id)
        detail = await get_count_detail(session, tenant.id, count.id)
        first = detail.lines[0]

        await set_line_counts(
            session, tenant_id=tenant.id, count_id=count.id, entries=[(first.id, 8)]
        )
        after = await get_count_detail(session, tenant.id, count.id)

    counted = {line.id: line.counted_qty for line in after.lines}
    assert counted[first.id] == 8
    assert after.counted_count == 1
    # 8 counted vs 10 on_hand -> delta -2 -> one diff
    assert after.diff_count == 1


@pytest.mark.asyncio
async def test_set_line_counts_rejects_unknown_line(sessionmaker, data_factory: TestDataFactory):
    from app.modules.ppe.inventory import InventoryCountNotFound, set_line_counts

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        count = await create_count(session, tenant_id=tenant.id)
        with pytest.raises(InventoryCountNotFound):
            await set_line_counts(
                session, tenant_id=tenant.id, count_id=count.id, entries=[("nope", 1)]
            )


@pytest.mark.asyncio
async def test_list_counts_filters_by_status_and_counts_lines(
    sessionmaker, data_factory: TestDataFactory
):
    from app.modules.ppe.inventory import list_counts

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        item = await _item(session, tenant.id, name="Каска")
        await _batch(session, tenant.id, item.id, batch_no="B-1", qty=10)
        count = await create_count(session, tenant_id=tenant.id)
        detail = await get_count_detail(session, tenant.id, count.id)
        from app.modules.ppe.inventory import set_line_counts

        await set_line_counts(
            session, tenant_id=tenant.id, count_id=count.id, entries=[(detail.lines[0].id, 9)]
        )
        await session.commit()
    async with sessionmaker() as session:
        drafts, total = await list_counts(session, tenant.id, status="draft")
        applied, _ = await list_counts(session, tenant.id, status="applied")

    assert total == 1
    assert drafts[0].line_count == 1
    assert drafts[0].counted_count == 1
    assert applied == []


@pytest.mark.asyncio
async def test_apply_emits_adjustments_only_for_changed_counted_lines(
    sessionmaker, data_factory: TestDataFactory
):
    from sqlalchemy import select as _select

    from app.models.ppe import PPEStockMovement
    from app.modules.ppe.inventory import apply_count, set_line_counts

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        item = await _item(session, tenant.id, name="Каска")
        b_low = await _batch(
            session, tenant.id, item.id, batch_no="B-1", qty=10
        )  # count 8 -> adjust
        b_same = await _batch(session, tenant.id, item.id, batch_no="B-2", qty=5)  # count 5 -> skip
        b_skip = await _batch(
            session, tenant.id, item.id, batch_no="B-3", qty=3
        )  # uncounted -> skip
        count = await create_count(session, tenant_id=tenant.id)
        detail = await get_count_detail(session, tenant.id, count.id)
        line_by_batch = {line.batch_id: line.id for line in detail.lines}

        await set_line_counts(
            session,
            tenant_id=tenant.id,
            count_id=count.id,
            entries=[(line_by_batch[b_low.id], 8), (line_by_batch[b_same.id], 5)],
        )
        applied = await apply_count(session, tenant_id=tenant.id, count_id=count.id, now=NOW)
        await session.refresh(b_low)
        await session.refresh(b_same)
        await session.refresh(b_skip)
        result = await session.execute(
            _select(PPEStockMovement).where(
                PPEStockMovement.tenant_id == tenant.id,
                PPEStockMovement.kind == "adjustment",
            )
        )
        movements = list(result.scalars().all())

    assert applied.status == "applied"
    assert applied.applied_at == NOW
    assert b_low.quantity == 8  # adjusted to counted
    assert b_same.quantity == 5  # unchanged (zero delta -> no movement)
    assert b_skip.quantity == 3  # uncounted -> untouched
    assert len(movements) == 1
    assert movements[0].ref_type == "ppe_inventory_count"
    assert movements[0].ref_id == count.id


@pytest.mark.asyncio
async def test_apply_uses_live_on_hand_not_snapshot(sessionmaker, data_factory: TestDataFactory):
    from app.modules.ppe.inventory import apply_count, set_line_counts
    from app.modules.ppe.stock import record_movement

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        item = await _item(session, tenant.id, name="Каска")
        batch = await _batch(session, tenant.id, item.id, batch_no="B-1", qty=10)
        count = await create_count(session, tenant_id=tenant.id)  # snapshot system_qty=10
        detail = await get_count_detail(session, tenant.id, count.id)
        # stock moves AFTER the snapshot: a writeoff of 4 -> live on_hand=6
        await record_movement(
            session, tenant_id=tenant.id, batch_id=batch.id, kind="writeoff", quantity=4
        )
        await set_line_counts(
            session,
            tenant_id=tenant.id,
            count_id=count.id,
            entries=[(detail.lines[0].id, 9)],
        )
        await apply_count(session, tenant_id=tenant.id, count_id=count.id, now=NOW)
        await session.refresh(batch)

    assert batch.quantity == 9  # set-to-absolute from LIVE 6, not snapshot 10


@pytest.mark.asyncio
async def test_apply_twice_is_rejected(sessionmaker, data_factory: TestDataFactory):
    from app.modules.ppe.inventory import (
        InventoryCountNotDraft,
        apply_count,
    )

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        count = await create_count(session, tenant_id=tenant.id)
        await apply_count(session, tenant_id=tenant.id, count_id=count.id, now=NOW)
        with pytest.raises(InventoryCountNotDraft):
            await apply_count(session, tenant_id=tenant.id, count_id=count.id, now=NOW)


@pytest.mark.asyncio
async def test_cancel_sets_status_and_writes_no_movements(
    sessionmaker, data_factory: TestDataFactory
):
    from app.modules.ppe.inventory import cancel_count

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        count = await create_count(session, tenant_id=tenant.id)
        cancelled = await cancel_count(session, tenant_id=tenant.id, count_id=count.id)

    assert cancelled.status == "cancelled"


@pytest.mark.asyncio
async def test_apply_empty_count_flips_to_applied_with_no_movements(
    sessionmaker, data_factory: TestDataFactory
):
    from sqlalchemy import select as _select

    from app.models.ppe import PPEStockMovement
    from app.modules.ppe.inventory import apply_count

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        count = await create_count(session, tenant_id=tenant.id)  # no batches -> zero lines
        applied = await apply_count(session, tenant_id=tenant.id, count_id=count.id, now=NOW)
        result = await session.execute(
            _select(PPEStockMovement).where(PPEStockMovement.tenant_id == tenant.id)
        )
        movements = list(result.scalars().all())

    assert applied.status == "applied"
    assert applied.applied_at == NOW
    assert movements == []


@pytest.mark.asyncio
async def test_cancel_rejects_non_draft(sessionmaker, data_factory: TestDataFactory):
    from app.modules.ppe.inventory import InventoryCountNotDraft, apply_count, cancel_count

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        count = await create_count(session, tenant_id=tenant.id)
        await apply_count(session, tenant_id=tenant.id, count_id=count.id, now=NOW)
        with pytest.raises(InventoryCountNotDraft):
            await cancel_count(session, tenant_id=tenant.id, count_id=count.id)
