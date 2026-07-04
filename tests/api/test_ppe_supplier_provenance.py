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
async def test_batch_create_unknown_supplier_400(async_client, make_auth_headers, sessionmaker, data_factory: TestDataFactory):
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
    assert r.status_code in (status.HTTP_400_BAD_REQUEST, status.HTTP_404_NOT_FOUND), r.text


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
