"""API contract for the PPE warehouse skeleton (W-A · TZ-3.2-V11-01):
CRUD, stock-levels aggregate, tenant isolation.

Per-tenant feature gating is deferred: the `warehouse` pilot-flag name is
reserved (docs/FEATURE_FLAGS.md) but its enforcement model
(app.models.feature.FeatureEnablement) currently has a cross-base FK bug
(FK to SharedBase `feature` from TenantBase `featureenablement`) that breaks
mapper configuration when imported. The skeleton endpoints stay additive and
admin-RBAC-protected; gating lands once that subsystem is repaired.
"""
from __future__ import annotations

import pytest
from fastapi import status
from httpx import AsyncClient

from app.models.models import RoleEnum
from app.schemas.ppe import PPEItemCategory
from tests.utils.factories import TestDataFactory


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
        f"/api/v1/ppe/stock/batches/{batch_id}", json={"quantity": 5}, headers=headers
    )
    assert patched.status_code == status.HTTP_200_OK
    assert patched.json()["quantity"] == 5


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
    fetched_b = await async_client.get(
        f"/api/v1/ppe/stock/batches/{batch_a}", headers=headers_b
    )
    assert fetched_b.status_code == status.HTTP_404_NOT_FOUND
