"""PPE norms CRUD: create/list/patch/delete, 409 duplicate, tenant isolation."""
from __future__ import annotations

import pytest
from fastapi import status
from httpx import AsyncClient

from app.models.models import Position, PPEItem, RoleEnum
from app.models.risk import RiskHazard

BASE = "/api/v1/ppe/norms"


async def _seed_refs(sessionmaker, data_factory, slug="test"):
    """Position + hazard + ppe item for the default test tenant."""
    tenant = await data_factory.ensure_tenant(slug=slug)
    company = await data_factory.create_company(tenant=tenant, name=f"PPE Co {slug}")
    async with sessionmaker() as session:
        position = Position(tenant_id=tenant.id, company_id=company.id, name="Сварщик")
        hazard = RiskHazard(tenant_id=tenant.id, code=f"weld-{slug}", title="Сварочные аэрозоли")
        item = PPEItem(tenant_id=tenant.id, name=f"Щиток сварщика {slug}", default_wear_days=365)
        session.add_all([position, hazard, item])
        await session.commit()
        return str(position.id), str(hazard.id), str(item.id)


@pytest.mark.asyncio
async def test_norm_crud_roundtrip(async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    position_id, hazard_id, item_id = await _seed_refs(sessionmaker, data_factory)

    resp = await async_client.post(BASE, headers=headers, json={
        "position_id": position_id, "hazard_id": hazard_id,
        "item_id": item_id, "quantity": 2, "interval_days": 180,
    })
    assert resp.status_code == status.HTTP_201_CREATED, resp.text
    body = resp.json()
    norm_id = body["id"]
    assert body["item_id"] == item_id
    assert body["item_name"]  # денормализовано из PPEItem.name
    assert body["quantity"] == 2

    listed = await async_client.get(BASE, headers=headers, params={"position_id": position_id})
    assert listed.status_code == status.HTTP_200_OK
    assert any(n["id"] == norm_id for n in listed.json()["items"])

    patched = await async_client.patch(f"{BASE}/{norm_id}", headers=headers, json={"quantity": 3})
    assert patched.status_code == status.HTTP_200_OK
    assert patched.json()["quantity"] == 3

    deleted = await async_client.delete(f"{BASE}/{norm_id}", headers=headers)
    assert deleted.status_code == status.HTTP_204_NO_CONTENT
    listed2 = await async_client.get(BASE, headers=headers)
    assert all(n["id"] != norm_id for n in listed2.json()["items"])


@pytest.mark.asyncio
async def test_duplicate_norm_409(async_client, make_auth_headers, sessionmaker, data_factory):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    position_id, hazard_id, item_id = await _seed_refs(sessionmaker, data_factory, slug="test")
    payload = {"position_id": position_id, "hazard_id": hazard_id, "item_id": item_id}
    first = await async_client.post(BASE, headers=headers, json=payload)
    assert first.status_code == status.HTTP_201_CREATED, first.text
    dup = await async_client.post(BASE, headers=headers, json=payload)
    assert dup.status_code == status.HTTP_409_CONFLICT, dup.text


@pytest.mark.asyncio
async def test_norm_foreign_refs_must_exist_in_tenant(async_client, make_auth_headers, sessionmaker, data_factory):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    position_id, hazard_id, _ = await _seed_refs(sessionmaker, data_factory)
    resp = await async_client.post(BASE, headers=headers, json={
        "position_id": position_id, "hazard_id": hazard_id, "item_id": "missing-item-id",
    })
    assert resp.status_code == status.HTTP_404_NOT_FOUND, resp.text
