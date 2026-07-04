"""Batch supplier provenance + transfer copies supplier (P10-06)."""

from __future__ import annotations

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import select

from app.models.models import RoleEnum
from app.models.ppe_registry import PPEStockBatch
from app.modules.ppe.stock import transfer_stock
from app.schemas.ppe import PPEItemCategory
from tests.utils.factories import TestDataFactory


async def _supplier(async_client, headers, name="Вендор") -> str:
    r = await async_client.post("/api/v1/ppe/suppliers", json={"name": name}, headers=headers)
    assert r.status_code == status.HTTP_201_CREATED, r.text
    return r.json()["id"]


async def _item(async_client, headers, name="Каска") -> str:
    r = await async_client.post(
        "/api/v1/ppe/items", json={"name": name, "category": PPEItemCategory.HEAD.value}, headers=headers
    )
    assert r.status_code == status.HTTP_201_CREATED, r.text
    return r.json()["id"]


@pytest.mark.asyncio
async def test_batch_create_stores_and_returns_supplier(async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    sid = await _supplier(async_client, headers)
    item_id = await _item(async_client, headers)

    r = await async_client.post(
        "/api/v1/ppe/stock/batches",
        json={"item_id": item_id, "batch_no": "B-1", "quantity": 10, "location": "A", "supplier_id": sid},
        headers=headers,
    )
    assert r.status_code == status.HTTP_201_CREATED, r.text
    assert r.json()["supplier_id"] == sid


@pytest.mark.asyncio
async def test_batch_create_unknown_supplier_404(async_client, make_auth_headers, sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    item_id = await _item(async_client, headers)
    r = await async_client.post(
        "/api/v1/ppe/stock/batches",
        json={"item_id": item_id, "batch_no": "B-1", "quantity": 1, "supplier_id": "nope"},
        headers=headers,
    )
    assert r.status_code == status.HTTP_404_NOT_FOUND, r.text


@pytest.mark.asyncio
async def test_transfer_copies_supplier_to_dest_batch(sessionmaker, data_factory: TestDataFactory):
    from app.models.models import PPEItem, PPESupplier

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        sup = PPESupplier(tenant_id=tenant.id, name="Вендор")
        session.add(sup)
        await session.flush()
        item = PPEItem(tenant_id=tenant.id, name="Каска")
        session.add(item)
        await session.flush()
        source = PPEStockBatch(
            tenant_id=tenant.id, item_id=item.id, batch_no="B-1",
            quantity=10, location="A", supplier_id=sup.id,
        )
        session.add(source)
        await session.flush()

        result = await transfer_stock(
            session, tenant_id=tenant.id, source_batch_id=source.id, to_location="B", quantity=4
        )
        dest = (
            await session.execute(select(PPEStockBatch).where(PPEStockBatch.id == result.dest_batch_id))
        ).scalar_one()
        assert dest.supplier_id == sup.id  # provenance copied


@pytest.mark.asyncio
async def test_transfer_into_existing_dest_keeps_dest_supplier(sessionmaker, data_factory: TestDataFactory):
    from app.models.models import PPEItem, PPESupplier

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        src_sup = PPESupplier(tenant_id=tenant.id, name="SrcVendor")
        dst_sup = PPESupplier(tenant_id=tenant.id, name="DstVendor")
        session.add_all([src_sup, dst_sup])
        await session.flush()
        item = PPEItem(tenant_id=tenant.id, name="Каска")
        session.add(item)
        await session.flush()
        source = PPEStockBatch(tenant_id=tenant.id, item_id=item.id, batch_no="B-1", quantity=10, location="A", supplier_id=src_sup.id)
        dest = PPEStockBatch(tenant_id=tenant.id, item_id=item.id, batch_no="B-1", quantity=2, location="B", supplier_id=dst_sup.id)
        session.add_all([source, dest])
        await session.flush()

        result = await transfer_stock(session, tenant_id=tenant.id, source_batch_id=source.id, to_location="B", quantity=3)
        merged = (await session.execute(select(PPEStockBatch).where(PPEStockBatch.id == result.dest_batch_id))).scalar_one()
        assert merged.id == dest.id            # merged into existing dest
        assert merged.quantity == 5            # 2 + 3
        assert merged.supplier_id == dst_sup.id  # existing provenance preserved, NOT overwritten by source


@pytest.mark.asyncio
async def test_batch_update_clears_supplier(async_client, make_auth_headers, sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    sid = await _supplier(async_client, headers)
    item_id = await _item(async_client, headers)
    created = await async_client.post(
        "/api/v1/ppe/stock/batches",
        json={"item_id": item_id, "batch_no": "B-1", "quantity": 5, "location": "A", "supplier_id": sid},
        headers=headers,
    )
    batch_id = created.json()["id"]
    patched = await async_client.patch(
        f"/api/v1/ppe/stock/batches/{batch_id}", json={"supplier_id": None}, headers=headers
    )
    assert patched.status_code == status.HTTP_200_OK, patched.text
    assert patched.json()["supplier_id"] is None


@pytest.mark.asyncio
async def test_item_preferred_supplier_roundtrip(async_client, make_auth_headers, sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    sid = await _supplier(async_client, headers)
    item_id = await _item(async_client, headers)

    patched = await async_client.patch(
        f"/api/v1/ppe/items/{item_id}", json={"preferred_supplier_id": sid}, headers=headers
    )
    assert patched.status_code == status.HTTP_200_OK, patched.text
    assert patched.json()["preferred_supplier_id"] == sid


@pytest.mark.asyncio
async def test_item_create_unknown_preferred_supplier_404(async_client, make_auth_headers, sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    from app.schemas.ppe import PPEItemCategory
    r = await async_client.post(
        "/api/v1/ppe/items",
        json={"name": "Каска2", "category": PPEItemCategory.HEAD.value, "preferred_supplier_id": "nope"},
        headers=headers,
    )
    assert r.status_code == status.HTTP_404_NOT_FOUND, r.text
