"""API contract for the PPE warehouse skeleton (W-A · TZ-3.2-V11-01):
CRUD, stock-levels aggregate, tenant isolation, and the per-tenant `warehouse`
pilot feature gate.

Per-tenant feature gating now lands: the `warehouse` pilot flag
(docs/FEATURE_FLAGS.md) gates every `/ppe/stock/*` route. Default-on — a tenant
only loses access by storing FeatureEnablement(on=False) for
Feature(code="warehouse"), in which case the routes 404. The cross-base FK bug
that previously blocked importing app.models.feature (FK to SharedBase `feature`
from TenantBase `featureenablement`, which broke create_all-first boot) was
fixed by dropping that ForeignKey — see tests/unit/test_feature_model_import.py.
"""

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
    default ("test") tenant used by ``make_auth_headers``."""
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


@pytest.mark.asyncio
async def test_create_list_get_patch_batch(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    item_id = await _seed_item(async_client, headers)

    created = await async_client.post(
        "/api/v1/ppe/stock/batches",
        json={
            "item_id": item_id,
            "batch_no": "B-100",
            "quantity": 25,
            "certificate_no": "CERT-1",
        },
        headers=headers,
    )
    assert created.status_code == status.HTTP_201_CREATED, created.text
    batch_id = created.json()["id"]
    assert created.json()["quantity"] == 25

    listed = await async_client.get("/api/v1/ppe/stock/batches", headers=headers)
    assert listed.status_code == status.HTTP_200_OK
    assert any(b["id"] == batch_id for b in listed.json()["items"])

    fetched = await async_client.get(f"/api/v1/ppe/stock/batches/{batch_id}", headers=headers)
    assert fetched.status_code == status.HTTP_200_OK
    assert fetched.json()["certificate_no"] == "CERT-1"

    patched = await async_client.patch(
        f"/api/v1/ppe/stock/batches/{batch_id}",
        json={"location": "Склад-2"},
        headers=headers,
    )
    assert patched.status_code == status.HTTP_200_OK
    assert patched.json()["location"] == "Склад-2"
    assert patched.json()["quantity"] == 25  # quantity unchanged: not patchable


@pytest.mark.asyncio
async def test_create_batch_unknown_item_404(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    resp = await async_client.post(
        "/api/v1/ppe/stock/batches",
        json={"item_id": "does-not-exist", "batch_no": "B-1", "quantity": 1},
        headers=headers,
    )
    assert resp.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_stock_levels_aggregate(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    item_id = await _seed_item(async_client, headers, name="Перчатки")
    for no, qty in (("B-1", 10), ("B-2", 7)):
        resp = await async_client.post(
            "/api/v1/ppe/stock/batches",
            json={"item_id": item_id, "batch_no": no, "quantity": qty},
            headers=headers,
        )
        assert resp.status_code == status.HTTP_201_CREATED, resp.text

    levels = await async_client.get("/api/v1/ppe/stock/levels", headers=headers)
    assert levels.status_code == status.HTTP_200_OK
    body = levels.json()
    row = next(r for r in body["items"] if r["item_id"] == item_id)
    assert row["total_quantity"] == 17
    assert row["batch_count"] == 2
    assert row["item_name"] == "Перчатки"


@pytest.mark.asyncio
async def test_batches_tenant_isolation(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await data_factory.ensure_tenant(slug="beta", session=session)
        await session.commit()
    headers_a = await make_auth_headers(RoleEnum.ADMIN)
    item_a = await _seed_item(async_client, headers_a)
    resp = await async_client.post(
        "/api/v1/ppe/stock/batches",
        json={"item_id": item_a, "batch_no": "B-1", "quantity": 3},
        headers=headers_a,
    )
    batch_a = resp.json()["id"]

    headers_b = await make_auth_headers(
        RoleEnum.ADMIN, tenant="beta", email="admin-beta@example.com"
    )
    listed_b = await async_client.get("/api/v1/ppe/stock/batches", headers=headers_b)
    assert all(b["id"] != batch_a for b in listed_b.json()["items"])
    fetched_b = await async_client.get(f"/api/v1/ppe/stock/batches/{batch_a}", headers=headers_b)
    assert fetched_b.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_stock_endpoints_default_on_without_flag(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    # No FeatureEnablement row -> warehouse defaults on -> routes serve normally.
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    listed = await async_client.get("/api/v1/ppe/stock/batches", headers=headers)
    assert listed.status_code == status.HTTP_200_OK
    levels = await async_client.get("/api/v1/ppe/stock/levels", headers=headers)
    assert levels.status_code == status.HTTP_200_OK


@pytest.mark.asyncio
async def test_stock_endpoints_readonly_when_feature_disabled(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    await _set_warehouse_flag(sessionmaker, data_factory, on=False)
    headers = await make_auth_headers(RoleEnum.ADMIN)

    # BIZ-61 срез-6 (разд. 61.2): выдан и отключён — чтение открыто…
    listed = await async_client.get("/api/v1/ppe/stock/batches", headers=headers)
    assert listed.status_code == status.HTTP_200_OK, listed.text
    levels = await async_client.get("/api/v1/ppe/stock/levels", headers=headers)
    assert levels.status_code == status.HTTP_200_OK, levels.text

    # …а мутация гейтится ДО тела (item lookup не успевает) и объяснена словами.
    created = await async_client.post(
        "/api/v1/ppe/stock/batches",
        json={"item_id": "irrelevant", "batch_no": "B-1", "quantity": 1},
        headers=headers,
    )
    assert created.status_code == status.HTTP_403_FORBIDDEN, created.text
    assert "MODULE_READ_ONLY" in created.text


@pytest.mark.asyncio
async def test_stock_endpoints_served_when_feature_enabled(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    await _set_warehouse_flag(sessionmaker, data_factory, on=True)
    headers = await make_auth_headers(RoleEnum.ADMIN)
    item_id = await _seed_item(async_client, headers)
    created = await async_client.post(
        "/api/v1/ppe/stock/batches",
        json={"item_id": item_id, "batch_no": "B-100", "quantity": 5},
        headers=headers,
    )
    assert created.status_code == status.HTTP_201_CREATED, created.text
    listed = await async_client.get("/api/v1/ppe/stock/batches", headers=headers)
    assert listed.status_code == status.HTTP_200_OK
