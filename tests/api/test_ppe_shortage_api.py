"""min_stock threshold + /ppe/stock/shortages endpoint (P10-06)."""

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
    """Seed Feature(code="warehouse") + FeatureEnablement(on=...) for the
    default ("test") tenant used by ``make_auth_headers``.

    Mirrors ``tests/api/test_ppe_warehouse_api.py::_set_warehouse_flag``.
    """
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


async def _seed_item(client, headers, *, name="Каска", min_stock=0):
    resp = await client.post(
        "/api/v1/ppe/items",
        json={"name": name, "category": PPEItemCategory.HEAD.value, "min_stock": min_stock},
        headers=headers,
    )
    assert resp.status_code == status.HTTP_201_CREATED, resp.text
    return resp.json()


async def _seed_batch(client, headers, item_id, *, no="B-1", qty=1):
    resp = await client.post(
        "/api/v1/ppe/stock/batches",
        json={"item_id": item_id, "batch_no": no, "quantity": qty},
        headers=headers,
    )
    assert resp.status_code == status.HTTP_201_CREATED, resp.text
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_item_create_and_patch_min_stock(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
):
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)

    created = await _seed_item(async_client, headers, min_stock=7)
    assert created["min_stock"] == 7

    patched = await async_client.patch(
        f"/api/v1/ppe/items/{created['id']}",
        json={"min_stock": 15},
        headers=headers,
    )
    assert patched.status_code == status.HTTP_200_OK, patched.text
    assert patched.json()["min_stock"] == 15


@pytest.mark.asyncio
async def test_shortages_lists_below_threshold_item(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
):
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    # warehouse defaults on (no FeatureEnablement row) — see test_ppe_warehouse_api.py.
    headers = await make_auth_headers(RoleEnum.ADMIN)
    item = await _seed_item(async_client, headers, name="Каска", min_stock=10)
    await _seed_batch(async_client, headers, item["id"], qty=3)

    resp = await async_client.get("/api/v1/ppe/stock/shortages", headers=headers)
    assert resp.status_code == status.HTTP_200_OK, resp.text
    body = resp.json()
    assert body["window_days"] == 90
    row = next(r for r in body["items"] if r["item_id"] == item["id"])
    assert row["min_stock"] == 10
    assert row["on_hand"] == 3
    assert row["deficit"] == 7
    assert row["below_threshold"] is True


@pytest.mark.asyncio
async def test_shortages_window_days_clamped(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
):
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    resp = await async_client.get("/api/v1/ppe/stock/shortages?window_days=0", headers=headers)
    assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@pytest.mark.asyncio
async def test_shortages_readable_when_warehouse_disabled(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
):
    # BIZ-61 срез-6 (разд. 61.2): модуль был выдан и отключён — чтение
    # остаётся открытым (read-only); 404 отвечает только «никогда не выдан».
    await _set_warehouse_flag(sessionmaker, data_factory, on=False)
    headers = await make_auth_headers(RoleEnum.ADMIN)
    resp = await async_client.get("/api/v1/ppe/stock/shortages", headers=headers)
    assert resp.status_code == status.HTTP_200_OK, resp.text
