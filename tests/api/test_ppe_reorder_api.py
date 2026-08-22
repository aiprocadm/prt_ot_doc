"""API contract for /stock/reorder + shortage supplier fields (P10-06)."""

from __future__ import annotations

import pytest
from fastapi import status
from httpx import AsyncClient

from app.models.models import RoleEnum
from app.schemas.ppe import PPEItemCategory
from tests.utils.factories import TestDataFactory


@pytest.mark.asyncio
async def test_reorder_groups_below_threshold_by_supplier(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
):
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)

    sup = await async_client.post("/api/v1/ppe/suppliers", json={"name": "Alpha"}, headers=headers)
    sid = sup.json()["id"]
    item = await async_client.post(
        "/api/v1/ppe/items",
        json={
            "name": "Каска",
            "category": PPEItemCategory.HEAD.value,
            "min_stock": 10,
            "preferred_supplier_id": sid,
        },
        headers=headers,
    )
    item_id = item.json()["id"]
    # on_hand 0 < min_stock 10 -> below threshold, deficit 10

    resp = await async_client.get("/api/v1/ppe/stock/reorder", headers=headers)
    assert resp.status_code == status.HTTP_200_OK, resp.text
    body = resp.json()
    grp = next(g for g in body["groups"] if g["supplier_id"] == sid)
    assert grp["supplier_name"] == "Alpha"
    line = next(ln for ln in grp["lines"] if ln["item_id"] == item_id)
    assert line["deficit"] == 10


@pytest.mark.asyncio
async def test_reorder_readable_when_feature_disabled(
    async_client, make_auth_headers, sessionmaker, data_factory: TestDataFactory
):
    from sqlalchemy import select

    from app.models.feature import Feature, FeatureEnablement

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        feature = (
            await session.execute(select(Feature).where(Feature.code == "warehouse"))
        ).scalar_one_or_none()
        if feature is None:
            feature = Feature(code="warehouse", title="Warehouse")
            session.add(feature)
            await session.flush()
        # Обновляем существующую выдачу, а не добавляем вторую строку: у
        # тестового арендатора модуль выдан явно (BIZ-61 срез-2). Дубль делал
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
            session.add(FeatureEnablement(tenant_id=tenant.id, feature_id=feature.id, on=False))
        else:
            enablement.on = False
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    # BIZ-61 срез-6 (разд. 61.2): модуль был выдан и отключён — чтение
    # остаётся открытым (read-only), 404 отвечает только «никогда не выдан».
    resp = await async_client.get("/api/v1/ppe/stock/reorder", headers=headers)
    assert resp.status_code == status.HTTP_200_OK, resp.text
