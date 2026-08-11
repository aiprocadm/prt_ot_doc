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
        # Обновляем существующую строку, а не добавляем вторую: у арендатора
        # уже есть выдача модуля (BIZ-61 срез-2 — модуль по умолчанию выключен,
        # поэтому тестовым арендаторам он выдаётся явно). Вставка дубля делала
        # ответ гейта неопределённым.
        enablement = (
            (
                await session.execute(
                    select(FeatureEnablement).where(
                        FeatureEnablement.tenant_id == tenant.id,
                        FeatureEnablement.feature_id == feature.id,
                    )
                )
            )
            .scalars()
            .first()
        )
        if enablement is None:
            session.add(FeatureEnablement(tenant_id=tenant.id, feature_id=feature.id, on=on))
        else:
            enablement.on = on
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


@pytest.mark.asyncio
async def test_patch_apply_flow_adjusts_stock(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
):
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    item_id = await _seed_item(async_client, headers)
    await _seed_batch(async_client, headers, item_id, batch_no="B-1", qty=10)

    created = await async_client.post(
        "/api/v1/ppe/stock/inventory/counts", json={}, headers=headers
    )
    count_id = created.json()["id"]
    line_id = created.json()["lines"][0]["id"]

    patched = await async_client.patch(
        f"/api/v1/ppe/stock/inventory/counts/{count_id}/lines",
        json={"entries": [{"line_id": line_id, "counted_qty": 7}]},
        headers=headers,
    )
    assert patched.status_code == status.HTTP_200_OK
    assert patched.json()["lines"][0]["counted_qty"] == 7
    assert patched.json()["lines"][0]["delta"] == -3
    assert patched.json()["diff_count"] == 1

    applied = await async_client.post(
        f"/api/v1/ppe/stock/inventory/counts/{count_id}/apply", headers=headers
    )
    assert applied.status_code == status.HTTP_200_OK
    assert applied.json()["status"] == "applied"

    levels = await async_client.get("/api/v1/ppe/stock/levels", headers=headers)
    total = next(
        lvl["total_quantity"] for lvl in levels.json()["items"] if lvl["item_id"] == item_id
    )
    assert total == 7


@pytest.mark.asyncio
async def test_apply_twice_returns_400(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
):
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    created = await async_client.post(
        "/api/v1/ppe/stock/inventory/counts", json={}, headers=headers
    )
    count_id = created.json()["id"]
    first = await async_client.post(
        f"/api/v1/ppe/stock/inventory/counts/{count_id}/apply", headers=headers
    )
    assert first.status_code == status.HTTP_200_OK
    second = await async_client.post(
        f"/api/v1/ppe/stock/inventory/counts/{count_id}/apply", headers=headers
    )
    assert second.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.asyncio
async def test_patch_negative_counted_is_422(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
):
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    created = await async_client.post(
        "/api/v1/ppe/stock/inventory/counts", json={}, headers=headers
    )
    count_id = created.json()["id"]
    resp = await async_client.patch(
        f"/api/v1/ppe/stock/inventory/counts/{count_id}/lines",
        json={"entries": [{"line_id": "x", "counted_qty": -5}]},
        headers=headers,
    )
    assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@pytest.mark.asyncio
async def test_cancel_sets_status(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
):
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    created = await async_client.post(
        "/api/v1/ppe/stock/inventory/counts", json={}, headers=headers
    )
    count_id = created.json()["id"]
    cancelled = await async_client.post(
        f"/api/v1/ppe/stock/inventory/counts/{count_id}/cancel", headers=headers
    )
    assert cancelled.status_code == status.HTTP_200_OK
    assert cancelled.json()["status"] == "cancelled"


@pytest.mark.asyncio
async def test_apply_nonexistent_count_is_404(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
):
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    resp = await async_client.post("/api/v1/ppe/stock/inventory/counts/nope/apply", headers=headers)
    assert resp.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_cancel_applied_count_is_400(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
):
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    created = await async_client.post(
        "/api/v1/ppe/stock/inventory/counts", json={}, headers=headers
    )
    count_id = created.json()["id"]
    await async_client.post(f"/api/v1/ppe/stock/inventory/counts/{count_id}/apply", headers=headers)
    resp = await async_client.post(
        f"/api/v1/ppe/stock/inventory/counts/{count_id}/cancel", headers=headers
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
