"""min_stock threshold + /ppe/stock/shortages endpoint (P10-06)."""

from __future__ import annotations

import pytest
from fastapi import status
from httpx import AsyncClient

from app.models.models import RoleEnum
from app.schemas.ppe import PPEItemCategory
from tests.utils.factories import TestDataFactory


async def _seed_item(client, headers, *, name="Каска", min_stock=0):
    resp = await client.post(
        "/api/v1/ppe/items",
        json={"name": name, "category": PPEItemCategory.HEAD.value, "min_stock": min_stock},
        headers=headers,
    )
    assert resp.status_code == status.HTTP_201_CREATED, resp.text
    return resp.json()


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
