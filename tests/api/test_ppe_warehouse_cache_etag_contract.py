"""HTTP cache (ETag / If-None-Match) contract for /api/v1/ppe/stock/batches
(W-A · TZ-3.2-V11-01). Mirrors tests/api/test_ppe_prescriptions_cache_etag_contract.py.
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


async def _seed_batch(
    async_client: AsyncClient, headers: dict, *, item_id: str, batch_no: str, quantity: int = 10
) -> dict:
    resp = await async_client.post(
        "/api/v1/ppe/stock/batches",
        json={"item_id": item_id, "batch_no": batch_no, "quantity": quantity},
        headers=headers,
    )
    assert resp.status_code == status.HTTP_201_CREATED, resp.text
    return resp.json()


@pytest.mark.asyncio
async def test_batches_hit_returns_304(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    item_id = await _seed_item(async_client, headers)
    await _seed_batch(async_client, headers, item_id=item_id, batch_no="B-1")

    first = await async_client.get("/api/v1/ppe/stock/batches", headers=headers)
    assert first.status_code == status.HTTP_200_OK
    etag = first.headers["ETag"]

    second = await async_client.get(
        "/api/v1/ppe/stock/batches", headers={**headers, "If-None-Match": etag}
    )
    assert second.status_code == status.HTTP_304_NOT_MODIFIED
    assert second.headers["ETag"] == etag
    assert second.content == b""


@pytest.mark.asyncio
async def test_batches_miss_with_bogus_etag(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    item_id = await _seed_item(async_client, headers)
    await _seed_batch(async_client, headers, item_id=item_id, batch_no="B-1")

    resp = await async_client.get(
        "/api/v1/ppe/stock/batches", headers={**headers, "If-None-Match": '"stale"'}
    )
    assert resp.status_code == status.HTTP_200_OK
    assert resp.json()["items"]


@pytest.mark.asyncio
async def test_batches_etag_changes_after_create(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    item_id = await _seed_item(async_client, headers)
    await _seed_batch(async_client, headers, item_id=item_id, batch_no="B-1")
    first = await async_client.get("/api/v1/ppe/stock/batches", headers=headers)
    initial = first.headers["ETag"]

    await _seed_batch(async_client, headers, item_id=item_id, batch_no="B-2")
    second = await async_client.get("/api/v1/ppe/stock/batches", headers=headers)
    assert second.headers["ETag"] != initial


@pytest.mark.asyncio
async def test_batches_filter_distinct_etag(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    item_id = await _seed_item(async_client, headers)
    await _seed_batch(async_client, headers, item_id=item_id, batch_no="B-1")

    unfiltered = await async_client.get("/api/v1/ppe/stock/batches", headers=headers)
    filtered = await async_client.get(
        f"/api/v1/ppe/stock/batches?item_id={item_id}", headers=headers
    )
    assert unfiltered.headers["ETag"] != filtered.headers["ETag"]


@pytest.mark.asyncio
async def test_batches_cross_tenant_anti_leak(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await data_factory.ensure_tenant(slug="beta", session=session)
        await session.commit()

    headers_a = await make_auth_headers(RoleEnum.ADMIN)
    item_a = await _seed_item(async_client, headers_a, name="Каска")
    await _seed_batch(async_client, headers_a, item_id=item_a, batch_no="B-1")
    resp_a = await async_client.get("/api/v1/ppe/stock/batches", headers=headers_a)
    etag_a = resp_a.headers["ETag"]

    headers_b = await make_auth_headers(
        RoleEnum.ADMIN, tenant="beta", email="admin-beta@example.com"
    )
    item_b = await _seed_item(async_client, headers_b, name="Каска")
    await _seed_batch(async_client, headers_b, item_id=item_b, batch_no="B-1")
    resp_b = await async_client.get("/api/v1/ppe/stock/batches", headers=headers_b)
    assert resp_b.headers["ETag"] != etag_a
