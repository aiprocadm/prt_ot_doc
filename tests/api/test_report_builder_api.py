"""API contract: flag gate, RBAC, CRUD, preview (P10-07 report builder)."""

from __future__ import annotations

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import select

from app.models.models import RoleEnum
from tests.utils.factories import TestDataFactory

BASE = "/api/v1/report-builder"


async def _enable_flag(sessionmaker, data_factory: TestDataFactory, *, on: bool = True) -> str:
    from app.models.feature import Feature, FeatureEnablement

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        feature = (
            await session.execute(select(Feature).where(Feature.code == "report_builder"))
        ).scalar_one_or_none()
        if feature is None:
            feature = Feature(code="report_builder", title="Конструктор отчётов")
            session.add(feature)
            await session.flush()
        session.add(FeatureEnablement(tenant_id=str(tenant.id), feature_id=feature.id, on=on))
        await session.commit()
        return str(tenant.id)


DEFINITION = {
    "name": "Мой отчёт",
    "dataset_code": "incidents",
    "config_json": {"columns": ["title", "status"]},
}


@pytest.mark.asyncio
async def test_flag_off_404(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory
):
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    resp = await async_client.get(f"{BASE}/datasets", headers=headers)
    assert resp.status_code == status.HTTP_404_NOT_FOUND  # default-off, без FeatureEnablement


@pytest.mark.asyncio
async def test_rbac_forbidden_role(async_client, make_auth_headers, sessionmaker, data_factory):
    await _enable_flag(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.WORKER)
    resp = await async_client.get(f"{BASE}/definitions", headers=headers)
    assert resp.status_code == status.HTTP_403_FORBIDDEN
    # line_manager: read — да, write — нет
    lm = await make_auth_headers(RoleEnum.LINE_MANAGER)
    ok = await async_client.get(f"{BASE}/definitions", headers=lm)
    assert ok.status_code == status.HTTP_200_OK
    denied = await async_client.post(f"{BASE}/definitions", json=DEFINITION, headers=lm)
    assert denied.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_datasets_catalog(async_client, make_auth_headers, sessionmaker, data_factory):
    await _enable_flag(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)
    resp = await async_client.get(f"{BASE}/datasets", headers=headers)
    assert resp.status_code == status.HTTP_200_OK
    body = resp.json()
    assert body["total"] == 4
    incidents = next(d for d in body["items"] if d["code"] == "incidents")
    status_col = next(c for c in incidents["columns"] if c["key"] == "status")
    assert status_col["kind"] == "enum"
    assert "reported" in status_col["enum_values"]
    assert status_col["ops"] == ["eq", "in"]


@pytest.mark.asyncio
async def test_crud_flow_and_conflicts(async_client, make_auth_headers, sessionmaker, data_factory):
    await _enable_flag(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)

    created = await async_client.post(f"{BASE}/definitions", json=DEFINITION, headers=headers)
    assert created.status_code == status.HTTP_201_CREATED, created.text
    definition_id = created.json()["id"]
    assert created.json()["is_system"] is False

    dup = await async_client.post(f"{BASE}/definitions", json=DEFINITION, headers=headers)
    assert dup.status_code == status.HTTP_409_CONFLICT

    bad = await async_client.post(
        f"{BASE}/definitions",
        json={**DEFINITION, "name": "Битый", "config_json": {"columns": ["bogus"]}},
        headers=headers,
    )
    assert bad.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    lst = await async_client.get(f"{BASE}/definitions", headers=headers)
    assert lst.status_code == status.HTTP_200_OK
    assert lst.json()["total"] == 1
    etag = lst.headers.get("etag")
    assert etag
    not_modified = await async_client.get(
        f"{BASE}/definitions", headers={**headers, "If-None-Match": etag}
    )
    assert not_modified.status_code == status.HTTP_304_NOT_MODIFIED

    patched = await async_client.patch(
        f"{BASE}/definitions/{definition_id}",
        json={"description": "обновлено"},
        headers=headers,
    )
    assert patched.status_code == status.HTTP_200_OK
    assert patched.json()["description"] == "обновлено"

    deleted = await async_client.delete(f"{BASE}/definitions/{definition_id}", headers=headers)
    assert deleted.status_code == status.HTTP_204_NO_CONTENT
    gone = await async_client.get(f"{BASE}/definitions/{definition_id}", headers=headers)
    assert gone.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_system_definition_immutable(
    async_client, make_auth_headers, sessionmaker, data_factory
):
    from app.models.models import ReportDefinition

    tenant_id = await _enable_flag(sessionmaker, data_factory)
    async with sessionmaker() as session:
        session.add(
            ReportDefinition(
                tenant_id=tenant_id,
                name="Системный",
                dataset_code="risks",
                config_json={},
                is_system=True,
            )
        )
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    lst = await async_client.get(f"{BASE}/definitions", headers=headers)
    system_id = next(i["id"] for i in lst.json()["items"] if i["is_system"])
    patched = await async_client.patch(
        f"{BASE}/definitions/{system_id}", json={"name": "x"}, headers=headers
    )
    assert patched.status_code == status.HTTP_400_BAD_REQUEST
    deleted = await async_client.delete(f"{BASE}/definitions/{system_id}", headers=headers)
    assert deleted.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.asyncio
async def test_preview_inline(async_client, make_auth_headers, sessionmaker, data_factory):
    await _enable_flag(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.LINE_MANAGER)  # read-роль может preview
    resp = await async_client.post(
        f"{BASE}/preview",
        json={"dataset_code": "incidents", "config_json": {"columns": ["title"]}},
        headers=headers,
    )
    assert resp.status_code == status.HTTP_200_OK, resp.text
    body = resp.json()
    assert body["total"] == 0 and body["rows"] == []
    assert body["columns"][0] == {"key": "title", "label": "Название", "kind": "string"}
    bad = await async_client.post(
        f"{BASE}/preview",
        json={"dataset_code": "incidents", "config_json": {"columns": ["bogus"]}},
        headers=headers,
    )
    assert bad.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
