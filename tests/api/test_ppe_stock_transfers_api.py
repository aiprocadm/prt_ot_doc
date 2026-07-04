"""API contract for PPE stock transfers (P10-06)."""

from __future__ import annotations

import pytest
from fastapi import status
from httpx import AsyncClient

from app.models.models import RoleEnum
from app.schemas.ppe import PPEItemCategory
from tests.utils.factories import TestDataFactory


async def _seed_item(async_client: AsyncClient, headers, *, name="Каска") -> str:
    resp = await async_client.post(
        "/api/v1/ppe/items",
        json={"name": name, "category": PPEItemCategory.HEAD.value},
        headers=headers,
    )
    assert resp.status_code == status.HTTP_201_CREATED, resp.text
    return resp.json()["id"]


async def _seed_batch(async_client, headers, item_id, *, no="B-1", qty=10, location="A") -> str:
    resp = await async_client.post(
        "/api/v1/ppe/stock/batches",
        json={"item_id": item_id, "batch_no": no, "quantity": qty, "location": location},
        headers=headers,
    )
    assert resp.status_code == status.HTTP_201_CREATED, resp.text
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_transfer_moves_stock_between_locations(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
):
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    item_id = await _seed_item(async_client, headers)
    batch_id = await _seed_batch(async_client, headers, item_id, qty=10, location="A")

    resp = await async_client.post(
        "/api/v1/ppe/stock/transfers",
        json={"source_batch_id": batch_id, "to_location": "B", "quantity": 3},
        headers=headers,
    )
    assert resp.status_code == status.HTTP_201_CREATED, resp.text
    body = resp.json()
    assert body["from_location"] == "A"
    assert body["to_location"] == "B"
    assert body["quantity"] == 3
    assert body["item_id"] == item_id

    levels = await async_client.get("/api/v1/ppe/stock/levels", headers=headers)
    row = next(r for r in levels.json()["items"] if r["item_id"] == item_id)
    assert row["total_quantity"] == 10


@pytest.mark.asyncio
async def test_transfer_insufficient_returns_400(
    async_client, make_auth_headers, sessionmaker, data_factory: TestDataFactory
):
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    item_id = await _seed_item(async_client, headers)
    batch_id = await _seed_batch(async_client, headers, item_id, qty=2, location="A")

    resp = await async_client.post(
        "/api/v1/ppe/stock/transfers",
        json={"source_batch_id": batch_id, "to_location": "B", "quantity": 5},
        headers=headers,
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST, resp.text


@pytest.mark.asyncio
async def test_transfer_same_location_returns_400(
    async_client, make_auth_headers, sessionmaker, data_factory: TestDataFactory
):
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    item_id = await _seed_item(async_client, headers)
    batch_id = await _seed_batch(async_client, headers, item_id, qty=5, location="A")

    resp = await async_client.post(
        "/api/v1/ppe/stock/transfers",
        json={"source_batch_id": batch_id, "to_location": "A", "quantity": 1},
        headers=headers,
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST, resp.text


@pytest.mark.asyncio
async def test_transfer_zero_quantity_returns_422(
    async_client, make_auth_headers, sessionmaker, data_factory: TestDataFactory
):
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    item_id = await _seed_item(async_client, headers)
    batch_id = await _seed_batch(async_client, headers, item_id, qty=5, location="A")

    resp = await async_client.post(
        "/api/v1/ppe/stock/transfers",
        json={"source_batch_id": batch_id, "to_location": "B", "quantity": 0},
        headers=headers,
    )
    assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY, resp.text


@pytest.mark.asyncio
async def test_transfer_unknown_source_returns_404(
    async_client, make_auth_headers, sessionmaker, data_factory: TestDataFactory
):
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    resp = await async_client.post(
        "/api/v1/ppe/stock/transfers",
        json={"source_batch_id": "nope", "to_location": "B", "quantity": 1},
        headers=headers,
    )
    assert resp.status_code == status.HTTP_404_NOT_FOUND, resp.text


@pytest.mark.asyncio
async def test_list_transfers_groups_pairs(
    async_client, make_auth_headers, sessionmaker, data_factory: TestDataFactory
):
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    item_id = await _seed_item(async_client, headers)
    batch_id = await _seed_batch(async_client, headers, item_id, qty=10, location="A")

    await async_client.post(
        "/api/v1/ppe/stock/transfers",
        json={"source_batch_id": batch_id, "to_location": "B", "quantity": 3},
        headers=headers,
    )
    await async_client.post(
        "/api/v1/ppe/stock/transfers",
        json={"source_batch_id": batch_id, "to_location": "C", "quantity": 2},
        headers=headers,
    )

    resp = await async_client.get("/api/v1/ppe/stock/transfers", headers=headers)
    assert resp.status_code == status.HTTP_200_OK, resp.text
    body = resp.json()
    assert body["total"] == 2
    tos = {row["to_location"] for row in body["items"]}
    assert tos == {"B", "C"}
    for row in body["items"]:
        assert row["from_location"] == "A"
        assert row["batch_no"] == "B-1"
        assert row["quantity"] in (2, 3)

    etag = resp.headers.get("etag")
    assert etag
    cached = await async_client.get(
        "/api/v1/ppe/stock/transfers", headers={**headers, "if-none-match": etag}
    )
    assert cached.status_code == status.HTTP_304_NOT_MODIFIED


@pytest.mark.asyncio
async def test_list_transfers_filter_by_item(
    async_client, make_auth_headers, sessionmaker, data_factory: TestDataFactory
):
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    item1 = await _seed_item(async_client, headers, name="Каска")
    item2 = await _seed_item(async_client, headers, name="Перчатки")
    b1 = await _seed_batch(async_client, headers, item1, no="B-1", qty=10, location="A")
    b2 = await _seed_batch(async_client, headers, item2, no="B-2", qty=10, location="A")
    await async_client.post(
        "/api/v1/ppe/stock/transfers",
        json={"source_batch_id": b1, "to_location": "B", "quantity": 3},
        headers=headers,
    )
    await async_client.post(
        "/api/v1/ppe/stock/transfers",
        json={"source_batch_id": b2, "to_location": "B", "quantity": 3},
        headers=headers,
    )

    resp = await async_client.get(
        "/api/v1/ppe/stock/transfers", params={"item_id": item1}, headers=headers
    )
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["item_id"] == item1


@pytest.mark.asyncio
async def test_levels_by_location_reflects_transfer(
    async_client, make_auth_headers, sessionmaker, data_factory: TestDataFactory
):
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    item_id = await _seed_item(async_client, headers)
    batch_id = await _seed_batch(async_client, headers, item_id, qty=10, location="A")

    await async_client.post(
        "/api/v1/ppe/stock/transfers",
        json={"source_batch_id": batch_id, "to_location": "B", "quantity": 4},
        headers=headers,
    )

    resp = await async_client.get("/api/v1/ppe/stock/levels/by-location", headers=headers)
    assert resp.status_code == status.HTTP_200_OK, resp.text
    rows = {r["location"]: r for r in resp.json()["items"] if r["item_id"] == item_id}
    assert rows["A"]["quantity"] == 6
    assert rows["B"]["quantity"] == 4
