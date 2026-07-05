"""API contract for PPE safety budget (P10-06)."""
from __future__ import annotations

import pytest
from fastapi import status
from httpx import AsyncClient

from app.models.models import RoleEnum
from app.schemas.ppe import PPEItemCategory
from tests.utils.factories import TestDataFactory

WIDE = {"name": "Всё время", "period_start": "2000-01-01", "period_end": "2100-01-01",
        "planned_amount": 10000}


async def _seed_item(async_client, headers, *, name="Каска"):
    resp = await async_client.post(
        "/api/v1/ppe/items",
        json={"name": name, "category": PPEItemCategory.HEAD.value},
        headers=headers,
    )
    assert resp.status_code == status.HTTP_201_CREATED, resp.text
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_budget_crud_and_actual(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
):
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)

    resp = await async_client.post("/api/v1/ppe/budgets", json=WIDE, headers=headers)
    assert resp.status_code == status.HTTP_201_CREATED, resp.text
    budget_id = resp.json()["id"]

    lst = await async_client.get("/api/v1/ppe/budgets", headers=headers)
    assert lst.status_code == status.HTTP_200_OK
    assert lst.json()["total"] == 1

    item_id = await _seed_item(async_client, headers)
    batch = await async_client.post(
        "/api/v1/ppe/stock/batches",
        json={"item_id": item_id, "batch_no": "B1", "quantity": 4, "unit_cost": 250},
        headers=headers,
    )
    assert batch.status_code == status.HTTP_201_CREATED, batch.text
    assert batch.json()["unit_cost"] == 250

    detail = await async_client.get(f"/api/v1/ppe/budgets/{budget_id}", headers=headers)
    assert detail.status_code == status.HTTP_200_OK, detail.text
    body = detail.json()
    assert body["actual_total"] == 1000.0
    assert body["remaining"] == 9000.0
    assert body["priced_receipt_count"] == 1
    assert body["by_category"][0]["category"] == "head"

    patched = await async_client.patch(
        f"/api/v1/ppe/budgets/{budget_id}", json={"planned_amount": 20000}, headers=headers
    )
    assert patched.status_code == status.HTTP_200_OK
    assert patched.json()["planned_amount"] == 20000

    dele = await async_client.delete(f"/api/v1/ppe/budgets/{budget_id}", headers=headers)
    assert dele.status_code == status.HTTP_204_NO_CONTENT
    gone = await async_client.get(f"/api/v1/ppe/budgets/{budget_id}", headers=headers)
    assert gone.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_period_order_422(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
):
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    resp = await async_client.post(
        "/api/v1/ppe/budgets",
        json={"name": "bad", "period_start": "2026-12-31", "period_end": "2026-01-01",
              "planned_amount": 1},
        headers=headers,
    )
    assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY, resp.text
