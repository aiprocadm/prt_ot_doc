"""API contract for PPE stock movements (P10-06)."""
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


async def _seed_batch(async_client, headers, item_id, *, no="B-1", qty=10) -> str:
    resp = await async_client.post(
        "/api/v1/ppe/stock/batches",
        json={"item_id": item_id, "batch_no": no, "quantity": qty},
        headers=headers,
    )
    assert resp.status_code == status.HTTP_201_CREATED, resp.text
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_receipt_movement_updates_levels(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
):
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    item_id = await _seed_item(async_client, headers)
    batch_id = await _seed_batch(async_client, headers, item_id, qty=10)

    resp = await async_client.post(
        "/api/v1/ppe/stock/movements",
        json={"batch_id": batch_id, "kind": "receipt", "quantity": 5, "reason": "поступление"},
        headers=headers,
    )
    assert resp.status_code == status.HTTP_201_CREATED, resp.text
    assert resp.json()["quantity_delta"] == 5

    levels = await async_client.get("/api/v1/ppe/stock/levels", headers=headers)
    row = next(r for r in levels.json()["items"] if r["item_id"] == item_id)
    assert row["total_quantity"] == 15


@pytest.mark.asyncio
async def test_writeoff_insufficient_returns_400(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
):
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    item_id = await _seed_item(async_client, headers)
    batch_id = await _seed_batch(async_client, headers, item_id, qty=2)

    resp = await async_client.post(
        "/api/v1/ppe/stock/movements",
        json={"batch_id": batch_id, "kind": "writeoff", "quantity": 5},
        headers=headers,
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.asyncio
async def test_issue_kind_rejected_on_manual_endpoint(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
):
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    item_id = await _seed_item(async_client, headers)
    batch_id = await _seed_batch(async_client, headers, item_id, qty=5)
    resp = await async_client.post(
        "/api/v1/ppe/stock/movements",
        json={"batch_id": batch_id, "kind": "issue", "quantity": 1},
        headers=headers,
    )
    assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@pytest.mark.asyncio
async def test_list_movements_filters_and_etag(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
):
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    item_id = await _seed_item(async_client, headers)
    batch_id = await _seed_batch(async_client, headers, item_id, qty=10)
    await async_client.post(
        "/api/v1/ppe/stock/movements",
        json={"batch_id": batch_id, "kind": "writeoff", "quantity": 1},
        headers=headers,
    )

    listed = await async_client.get(
        f"/api/v1/ppe/stock/movements?batch_id={batch_id}", headers=headers
    )
    assert listed.status_code == status.HTTP_200_OK
    kinds = {m["kind"] for m in listed.json()["items"]}
    assert "writeoff" in kinds  # includes the opening receipt + writeoff
    etag = listed.headers.get("etag")
    assert etag
    again = await async_client.get(
        f"/api/v1/ppe/stock/movements?batch_id={batch_id}",
        headers={**headers, "if-none-match": etag},
    )
    assert again.status_code == status.HTTP_304_NOT_MODIFIED


@pytest.mark.asyncio
async def test_movements_tenant_isolation(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
):
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await data_factory.ensure_tenant(slug="beta", session=session)
        await session.commit()
    headers_a = await make_auth_headers(RoleEnum.ADMIN)
    item_a = await _seed_item(async_client, headers_a)
    batch_a = await _seed_batch(async_client, headers_a, item_a, qty=5)

    headers_b = await make_auth_headers(
        RoleEnum.ADMIN, tenant="beta", email="admin-beta@example.com"
    )
    resp = await async_client.post(
        "/api/v1/ppe/stock/movements",
        json={"batch_id": batch_a, "kind": "receipt", "quantity": 1},
        headers=headers_b,
    )
    assert resp.status_code == status.HTTP_404_NOT_FOUND  # batch invisible cross-tenant
