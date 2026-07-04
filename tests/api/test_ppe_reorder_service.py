"""Supplier resolution (explicit -> history) + reorder draft (P10-06)."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from app.models.models import PPEItem, PPESupplier
from app.models.ppe_registry import PPEStockBatch
from app.modules.ppe.stock import ShortageRow, build_reorder_draft, compute_shortages
from tests.utils.factories import TestDataFactory

NOW = datetime(2026, 7, 4, tzinfo=timezone.utc)


async def _item(session, tenant_id, *, name, min_stock, preferred=None):
    it = PPEItem(tenant_id=tenant_id, name=name, min_stock=min_stock, preferred_supplier_id=preferred)
    session.add(it)
    await session.flush()
    return it


async def _batch(session, tenant_id, item_id, *, qty, supplier_id=None, received=None, no="B"):
    b = PPEStockBatch(
        tenant_id=tenant_id, item_id=item_id, batch_no=no, quantity=qty,
        location="A", supplier_id=supplier_id, received_at=received,
    )
    session.add(b)
    await session.flush()
    return b


@pytest.mark.asyncio
async def test_explicit_supplier_wins(sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        exp = PPESupplier(tenant_id=tenant.id, name="Explicit")
        hist = PPESupplier(tenant_id=tenant.id, name="History")
        session.add_all([exp, hist])
        await session.flush()
        item = await _item(session, tenant.id, name="Каска", min_stock=10, preferred=exp.id)
        await _batch(session, tenant.id, item.id, qty=1, supplier_id=hist.id, received=date(2026, 6, 1))

        rows = await compute_shortages(session, tenant.id, now=NOW)
        row = next(r for r in rows if r.item_id == item.id)
        assert row.supplier_id == exp.id
        assert row.supplier_name == "Explicit"
        assert row.supplier_source == "explicit"


@pytest.mark.asyncio
async def test_history_fallback_picks_latest(sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        old = PPESupplier(tenant_id=tenant.id, name="Old")
        new = PPESupplier(tenant_id=tenant.id, name="New")
        session.add_all([old, new])
        await session.flush()
        item = await _item(session, tenant.id, name="Каска", min_stock=10)  # no preferred
        await _batch(session, tenant.id, item.id, qty=1, supplier_id=old.id, received=date(2026, 1, 1), no="OLD")
        await _batch(session, tenant.id, item.id, qty=1, supplier_id=new.id, received=date(2026, 6, 1), no="NEW")

        rows = await compute_shortages(session, tenant.id, now=NOW)
        row = next(r for r in rows if r.item_id == item.id)
        assert row.supplier_id == new.id
        assert row.supplier_source == "history"


@pytest.mark.asyncio
async def test_no_supplier_when_none(sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        item = await _item(session, tenant.id, name="Каска", min_stock=10)
        await _batch(session, tenant.id, item.id, qty=1)  # no supplier
        rows = await compute_shortages(session, tenant.id, now=NOW)
        row = next(r for r in rows if r.item_id == item.id)
        assert row.supplier_id is None
        assert row.supplier_source is None


@pytest.mark.asyncio
async def test_soft_deleted_resolved_supplier_is_none(sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        dead = PPESupplier(tenant_id=tenant.id, name="Dead", deleted_at=NOW)
        session.add(dead)
        await session.flush()
        item = await _item(session, tenant.id, name="Каска", min_stock=10, preferred=dead.id)
        await _batch(session, tenant.id, item.id, qty=1)
        rows = await compute_shortages(session, tenant.id, now=NOW)
        row = next(r for r in rows if r.item_id == item.id)
        assert row.supplier_id is None
        assert row.supplier_source is None


@pytest.mark.asyncio
async def test_explicit_soft_deleted_falls_back_to_history(sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        dead = PPESupplier(tenant_id=tenant.id, name="DeadExplicit", deleted_at=NOW)
        live = PPESupplier(tenant_id=tenant.id, name="LiveHistory")
        session.add_all([dead, live])
        await session.flush()
        item = await _item(session, tenant.id, name="Каска", min_stock=10, preferred=dead.id)
        await _batch(session, tenant.id, item.id, qty=1, supplier_id=live.id, received=date(2026, 6, 1))
        rows = await compute_shortages(session, tenant.id, now=NOW)
        row = next(r for r in rows if r.item_id == item.id)
        assert row.supplier_id == live.id
        assert row.supplier_source == "history"


def _row(item_id, deficit, below, sid, sname):
    return ShortageRow(
        item_id=item_id, item_name=item_id, min_stock=10, on_hand=0, deficit=deficit,
        below_threshold=below, avg_daily_consumption=0.0, days_to_depletion=None,
        projected_breach_date=None, supplier_id=sid, supplier_name=sname,
        supplier_inn=None, supplier_contact=None, supplier_source="explicit" if sid else None,
    )


def test_build_reorder_draft_groups_by_supplier():
    rows = [
        _row("i1", 5, True, "s1", "Alpha"),
        _row("i2", 3, True, "s1", "Alpha"),
        _row("i3", 2, True, None, None),      # unassigned
        _row("i4", 9, False, "s1", "Alpha"),  # not below-threshold -> excluded
    ]
    draft = build_reorder_draft(rows)
    by_supplier = {g.supplier_id: g for g in draft.groups}
    assert by_supplier["s1"].line_count == 2
    assert by_supplier["s1"].total_deficit == 8
    assert by_supplier[None].line_count == 1          # unassigned group present
    assert draft.groups[-1].supplier_id is None        # unassigned sorts last
    assert draft.total_lines == 3
    assert draft.total_deficit == 10


def test_build_reorder_draft_sorts_named_suppliers_before_unassigned():
    rows = [
        _row("i0", 1, True, None, None),      # unassigned
        _row("i1", 2, True, "sB", "Beta"),    # inserted before Alpha
        _row("i2", 3, True, "sA", "Alpha"),
    ]
    draft = build_reorder_draft(rows)
    order = [g.supplier_name for g in draft.groups]
    assert order == ["Alpha", "Beta", None]   # name asc, unassigned last
