"""ORM round-trip for PPESupplier + batch/item provenance FKs (P10-06)."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models.models import PPESupplier
from app.models.ppe_registry import PPEItem, PPEStockBatch


@pytest.mark.asyncio
async def test_supplier_round_trip(sessionmaker, data_factory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        sup = PPESupplier(
            tenant_id=tenant.id,
            name="ООО Спецодежда",
            inn="7701234567",
            contact_email="sales@example.com",
            contact_phone="+7 495 000-00-00",
        )
        session.add(sup)
        await session.flush()

        item = PPEItem(tenant_id=tenant.id, name="Каска", preferred_supplier_id=sup.id)
        session.add(item)
        await session.flush()
        batch = PPEStockBatch(
            tenant_id=tenant.id,
            item_id=item.id,
            batch_no="B-1",
            quantity=5,
            location="A",
            supplier_id=sup.id,
        )
        session.add(batch)
        await session.flush()

        loaded = (
            await session.execute(select(PPESupplier).where(PPESupplier.id == sup.id))
        ).scalar_one()
        assert loaded.name == "ООО Спецодежда"
        assert loaded.inn == "7701234567"
        assert item.preferred_supplier_id == sup.id
        assert batch.supplier_id == sup.id


@pytest.mark.asyncio
async def test_supplier_name_unique_per_tenant(sessionmaker, data_factory):
    from sqlalchemy.exc import IntegrityError

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        session.add(PPESupplier(tenant_id=tenant.id, name="Дубль"))
        await session.flush()
        session.add(PPESupplier(tenant_id=tenant.id, name="Дубль"))
        with pytest.raises(IntegrityError):
            await session.flush()
