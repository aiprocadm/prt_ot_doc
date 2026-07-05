"""DB-level CRUD for the PPE safety budget service (P10-06)."""
from __future__ import annotations

from datetime import date

import pytest

from app.modules.ppe.budget import (
    BudgetNotFound,
    create_budget,
    get_budget,
    list_budgets,
    soft_delete_budget,
    update_budget,
)
from tests.utils.factories import TestDataFactory

Y = dict(period_start=date(2026, 1, 1), period_end=date(2026, 12, 31))


@pytest.mark.asyncio
async def test_create_get(sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        t = await data_factory.ensure_tenant(session=session)
        b = await create_budget(session, tenant_id=t.id, name="2026", planned_amount=1000, **Y)
        got = await get_budget(session, t.id, b.id)
        assert got.name == "2026"
        assert float(got.planned_amount) == 1000.0


@pytest.mark.asyncio
async def test_list_excludes_soft_deleted(sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        t = await data_factory.ensure_tenant(session=session)
        a = await create_budget(session, tenant_id=t.id, name="A", planned_amount=1, **Y)
        await create_budget(session, tenant_id=t.id, name="B", planned_amount=1, **Y)
        await soft_delete_budget(session, t.id, a.id)
        items, total = await list_budgets(session, t.id, limit=50, offset=0)
        assert total == 1
        assert [x.name for x in items] == ["B"]


@pytest.mark.asyncio
async def test_update_allowlist_and_missing(sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        t = await data_factory.ensure_tenant(session=session)
        b = await create_budget(session, tenant_id=t.id, name="Old", planned_amount=1, **Y)
        upd = await update_budget(session, t.id, b.id, name="New", planned_amount=2, bogus="x")
        assert upd.name == "New"
        assert float(upd.planned_amount) == 2.0
        assert not hasattr(upd, "bogus")
        with pytest.raises(BudgetNotFound):
            await get_budget(session, t.id, "nope")


@pytest.mark.asyncio
async def test_tenant_isolation(sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        t1 = await data_factory.ensure_tenant(session=session)
        t2 = await data_factory.ensure_tenant(session=session, slug="other")
        b = await create_budget(session, tenant_id=t1.id, name="T1", planned_amount=1, **Y)
        with pytest.raises(BudgetNotFound):
            await get_budget(session, t2.id, b.id)
