"""API tests for the PPE inventory-count slice (P10-06)."""

from __future__ import annotations

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import select

from app.models.feature import Feature, FeatureEnablement
from app.models.models import RoleEnum
from app.schemas.ppe import PPEItemCategory
from tests.utils.factories import TestDataFactory


async def _set_warehouse_flag(sessionmaker, data_factory: TestDataFactory, *, on: bool) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        feature = (
            await session.execute(select(Feature).where(Feature.code == "warehouse"))
        ).scalar_one_or_none()
        if feature is None:
            feature = Feature(code="warehouse", title="Warehouse")
            session.add(feature)
            await session.flush()
        session.add(FeatureEnablement(tenant_id=tenant.id, feature_id=feature.id, on=on))
        await session.commit()


async def _seed_item(async_client: AsyncClient, headers: dict, *, name: str = "Каска") -> str:
    resp = await async_client.post(
        "/api/v1/ppe/items",
        json={"name": name, "category": PPEItemCategory.HEAD.value},
        headers=headers,
    )
    assert resp.status_code == status.HTTP_201_CREATED, resp.text
    return resp.json()["id"]


async def _seed_batch(
    async_client: AsyncClient, headers: dict, item_id: str, *, batch_no: str, qty: int
) -> str:
    resp = await async_client.post(
        "/api/v1/ppe/stock/batches",
        json={"item_id": item_id, "batch_no": batch_no, "quantity": qty},
        headers=headers,
    )
    assert resp.status_code == status.HTTP_201_CREATED, resp.text
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_create_seeds_lines_and_get_returns_detail(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
):
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    item_id = await _seed_item(async_client, headers)
    await _seed_batch(async_client, headers, item_id, batch_no="B-1", qty=10)

    created = await async_client.post(
        "/api/v1/ppe/stock/inventory/counts", json={"note": "июль"}, headers=headers
    )
    assert created.status_code == status.HTTP_201_CREATED, created.text
    body = created.json()
    assert body["status"] == "draft"
    assert body["line_count"] == 1
    assert len(body["lines"]) == 1
    assert body["lines"][0]["system_qty"] == 10
    assert body["lines"][0]["counted_qty"] is None
    count_id = body["id"]

    listed = await async_client.get("/api/v1/ppe/stock/inventory/counts", headers=headers)
    assert listed.status_code == status.HTTP_200_OK
    assert any(c["id"] == count_id for c in listed.json()["items"])

    fetched = await async_client.get(
        f"/api/v1/ppe/stock/inventory/counts/{count_id}", headers=headers
    )
    assert fetched.status_code == status.HTTP_200_OK
    assert fetched.json()["lines"][0]["on_hand"] == 10


@pytest.mark.asyncio
async def test_list_etag_304(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
):
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    first = await async_client.get("/api/v1/ppe/stock/inventory/counts", headers=headers)
    assert first.status_code == status.HTTP_200_OK
    etag = first.headers["ETag"]
    second = await async_client.get(
        "/api/v1/ppe/stock/inventory/counts", headers={**headers, "If-None-Match": etag}
    )
    assert second.status_code == status.HTTP_304_NOT_MODIFIED


@pytest.mark.asyncio
async def test_counts_gated_by_warehouse_flag(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
):
    await _set_warehouse_flag(sessionmaker, data_factory, on=False)
    headers = await make_auth_headers(RoleEnum.ADMIN)
    resp = await async_client.get("/api/v1/ppe/stock/inventory/counts", headers=headers)
    assert resp.status_code == status.HTTP_404_NOT_FOUND
    assert "warehouse" in resp.text.lower()


@pytest.mark.asyncio
async def test_get_cross_tenant_is_404(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
):
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await data_factory.ensure_tenant(slug="beta", session=session)
        await session.commit()
    headers_a = await make_auth_headers(RoleEnum.ADMIN)
    created = await async_client.post(
        "/api/v1/ppe/stock/inventory/counts", json={}, headers=headers_a
    )
    count_id = created.json()["id"]

    headers_b = await make_auth_headers(
        RoleEnum.ADMIN, tenant="beta", email="admin-beta@example.com"
    )
    fetched = await async_client.get(
        f"/api/v1/ppe/stock/inventory/counts/{count_id}", headers=headers_b
    )
    assert fetched.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_create_scope_item_missing_is_404(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
):
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    resp = await async_client.post(
        "/api/v1/ppe/stock/inventory/counts",
        json={"scope_item_id": "does-not-exist"},
        headers=headers,
    )
    assert resp.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_create_scope_item_filters_lines(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
):
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    item_a = await _seed_item(async_client, headers, name="A")
    item_b = await _seed_item(async_client, headers, name="B")
    await _seed_batch(async_client, headers, item_a, batch_no="A-1", qty=5)
    await _seed_batch(async_client, headers, item_b, batch_no="B-1", qty=5)

    created = await async_client.post(
        "/api/v1/ppe/stock/inventory/counts",
        json={"scope_item_id": item_a},
        headers=headers,
    )
    assert created.status_code == status.HTTP_201_CREATED, created.text
    body = created.json()
    assert body["line_count"] == 1
    assert body["lines"][0]["batch_no"] == "A-1"
