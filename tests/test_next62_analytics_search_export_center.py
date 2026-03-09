from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.projections.models import ExportJob, PackageReadModel, SearchIndexEntry


@pytest.mark.anyio
async def test_analytics_and_trends_endpoints(async_client, sessionmaker, data_factory):
    async with sessionmaker() as session:  # type: AsyncSession
        tenant = await data_factory.ensure_tenant(session=session)
        session.add(PackageReadModel(tenant_id=tenant.id, package_id="pkg-1", status="in_progress"))
        await session.commit()

    response = await async_client.get("/api/v1/analytics/dashboard/executive")
    assert response.status_code == 200
    assert "dashboard" in response.json()

    trend = await async_client.get("/api/v1/analytics/trends/incidents")
    assert trend.status_code == 200
    assert trend.json()["metric"] == "incidents"


@pytest.mark.anyio
async def test_search_over_projection_index(async_client, sessionmaker, data_factory):
    async with sessionmaker() as session:  # type: AsyncSession
        tenant = await data_factory.ensure_tenant(session=session)
        session.add(
            SearchIndexEntry(
                tenant_id=tenant.id,
                entity_type="person",
                entity_id="person-1",
                title="Иван Иванов",
                route="/persons/person-1",
                search_text="Иван Иванов",
            )
        )
        await session.commit()

    response = await async_client.get("/api/v1/search", params={"q": "Иван", "entity_types": "person"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["items"]
    assert payload["items"][0]["entity_type"] == "person"


@pytest.mark.anyio
async def test_export_center_idempotent_creation(async_client, sessionmaker, data_factory):
    async with sessionmaker() as session:  # type: AsyncSession
        await data_factory.ensure_tenant(session=session)
        await session.commit()

    headers = {"Idempotency-Key": "same-export"}
    body = {"export_type": "training_matrix", "scope_json": {"scope": "tenant"}, "filters_json": {"status": "all"}}
    r1 = await async_client.post("/api/v1/exports", json=body, headers=headers)
    assert r1.status_code == 201
    r2 = await async_client.post("/api/v1/exports", json=body, headers=headers)
    assert r2.status_code == 201
    assert r1.json()["id"] == r2.json()["id"]

    details = await async_client.get(f"/api/v1/exports/{r1.json()['id']}")
    assert details.status_code == 200


@pytest.mark.anyio
async def test_client_portal_internal_requests_patch(async_client, sessionmaker, data_factory):
    async with sessionmaker() as session:  # type: AsyncSession
        await data_factory.ensure_tenant(session=session)
        session.add(
            ExportJob(
                tenant_id=(await data_factory.ensure_tenant(session=session)).id,
                export_type="dummy",
                scope_json={},
                filters_json={},
                status="done",
            )
        )
        await session.commit()

    created = await async_client.post("/api/v1/client-portal/requests", json={"title": "Need update", "body": "Please refresh package"})
    assert created.status_code == 201
    req_id = created.json()["id"]
    patched = await async_client.patch(f"/api/v1/portal-requests/{req_id}", json={"status": "in_progress"})
    assert patched.status_code == 200
    assert patched.json()["status"] == "in_progress"
