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


@pytest.mark.asyncio
async def test_norms_are_tenant_isolated(async_client, make_auth_headers, sessionmaker, data_factory):
    """Foreign tenant's norm and refs are invisible: 404 on read/patch/delete and on create with foreign refs."""
    headers = await make_auth_headers(RoleEnum.ADMIN)  # tenant slug "test"
    f_position_id, f_hazard_id, f_item_id = await _seed_refs(sessionmaker, data_factory, slug="other")

    # create a norm directly in the foreign tenant
    from app.models.models import PPENorm
    async with sessionmaker() as session:
        foreign_tenant = await data_factory.ensure_tenant(slug="other", session=session)
        norm = PPENorm(
            tenant_id=foreign_tenant.id, position_id=f_position_id, hazard_id=f_hazard_id,
            item_id=f_item_id, item_name="Чужая норма", quantity=1, interval_days=365,
        )
        session.add(norm)
        await session.commit()
        foreign_norm_id = str(norm.id)

    assert (await async_client.get(f"{BASE}/{foreign_norm_id}", headers=headers)).status_code == status.HTTP_404_NOT_FOUND
    assert (await async_client.patch(f"{BASE}/{foreign_norm_id}", headers=headers, json={"quantity": 5})).status_code == status.HTTP_404_NOT_FOUND
    assert (await async_client.delete(f"{BASE}/{foreign_norm_id}", headers=headers)).status_code == status.HTTP_404_NOT_FOUND

    # create with another tenant's refs → 404
    resp = await async_client.post(BASE, headers=headers, json={
        "position_id": f_position_id, "hazard_id": f_hazard_id, "item_id": f_item_id,
    })
    assert resp.status_code == status.HTTP_404_NOT_FOUND, resp.text

    # foreign norm is absent from our list
    listed = await async_client.get(BASE, headers=headers)
    assert all(n["id"] != foreign_norm_id for n in listed.json()["items"])


@pytest.mark.asyncio
async def test_same_item_norm_duplicate_caught_by_item_id(async_client, make_auth_headers, sessionmaker, data_factory):
    """Renaming the catalog item must not allow a second norm for the same item."""
    headers = await make_auth_headers(RoleEnum.ADMIN)
    position_id, hazard_id, item_id = await _seed_refs(sessionmaker, data_factory)

    first = await async_client.post(BASE, headers=headers, json={
        "position_id": position_id, "hazard_id": hazard_id, "item_id": item_id,
    })
    assert first.status_code == status.HTTP_201_CREATED, first.text

    renamed = await async_client.patch(f"/api/v1/ppe/items/{item_id}", headers=headers,
                                       json={"name": "Щиток сварщика (переименован)"})
    assert renamed.status_code == status.HTTP_200_OK, renamed.text

    dup = await async_client.post(BASE, headers=headers, json={
        "position_id": position_id, "hazard_id": hazard_id, "item_id": item_id,
    })
    assert dup.status_code == status.HTTP_409_CONFLICT, dup.text
