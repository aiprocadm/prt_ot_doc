"""API contract for the PPE supplier directory (P10-06)."""

from __future__ import annotations

import pytest
from fastapi import status
from httpx import AsyncClient

from app.models.feature import Feature, FeatureEnablement
from app.models.models import RoleEnum
from tests.utils.factories import TestDataFactory


async def _set_warehouse_flag(sessionmaker, data_factory, *, on: bool):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        from sqlalchemy import select
        feature = (
            await session.execute(select(Feature).where(Feature.code == "warehouse"))
        ).scalar_one_or_none()
        if feature is None:
            feature = Feature(code="warehouse", title="Warehouse")
            session.add(feature)
            await session.flush()
        session.add(FeatureEnablement(tenant_id=tenant.id, feature_id=feature.id, on=on))
        await session.commit()


@pytest.mark.asyncio
async def test_supplier_crud_roundtrip(async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)

    created = await async_client.post(
        "/api/v1/ppe/suppliers",
        json={"name": "Вендор", "inn": "7701234567", "contact_email": "s@ex.com"},
        headers=headers,
    )
    assert created.status_code == status.HTTP_201_CREATED, created.text
    sid = created.json()["id"]

    listed = await async_client.get("/api/v1/ppe/suppliers", headers=headers)
    assert listed.status_code == status.HTTP_200_OK
    assert any(s["id"] == sid for s in listed.json()["items"])

    patched = await async_client.patch(
        f"/api/v1/ppe/suppliers/{sid}", json={"name": "Вендор-2"}, headers=headers
    )
    assert patched.status_code == status.HTTP_200_OK
    assert patched.json()["name"] == "Вендор-2"

    deleted = await async_client.delete(f"/api/v1/ppe/suppliers/{sid}", headers=headers)
    assert deleted.status_code == status.HTTP_204_NO_CONTENT
    gone = await async_client.get(f"/api/v1/ppe/suppliers/{sid}", headers=headers)
    assert gone.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_duplicate_name_returns_409(async_client, make_auth_headers, sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    await async_client.post("/api/v1/ppe/suppliers", json={"name": "Dup"}, headers=headers)
    dup = await async_client.post("/api/v1/ppe/suppliers", json={"name": "Dup"}, headers=headers)
    assert dup.status_code == status.HTTP_409_CONFLICT, dup.text


@pytest.mark.asyncio
async def test_supplier_empty_name_returns_422(async_client, make_auth_headers, sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    resp = await async_client.post("/api/v1/ppe/suppliers", json={"name": ""}, headers=headers)
    assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY, resp.text


@pytest.mark.asyncio
async def test_suppliers_404_when_feature_disabled(async_client, make_auth_headers, sessionmaker, data_factory: TestDataFactory):
    await _set_warehouse_flag(sessionmaker, data_factory, on=False)
    headers = await make_auth_headers(RoleEnum.ADMIN)
    listed = await async_client.get("/api/v1/ppe/suppliers", headers=headers)
    assert listed.status_code == status.HTTP_404_NOT_FOUND
