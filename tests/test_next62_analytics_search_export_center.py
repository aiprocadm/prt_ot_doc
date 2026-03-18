from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import RoleEnum
from app.modules.projections.models import ExportJob, PackageReadModel, SearchIndexEntry


@pytest.mark.anyio
async def test_analytics_and_trends_endpoints(async_client, sessionmaker, data_factory, make_auth_headers):
    async with sessionmaker() as session:  # type: AsyncSession
        tenant = await data_factory.ensure_tenant(session=session)
        session.add(PackageReadModel(tenant_id=tenant.id, package_id="pkg-1", status="in_progress"))
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN)
    response = await async_client.get("/api/v1/analytics/dashboard/executive", headers={**headers, "X-Tenant": "test"})
    assert response.status_code == 200
    assert "dashboard" in response.json()

    trend = await async_client.get("/api/v1/analytics/trends/incidents", headers={**headers, "X-Tenant": "test"})
    assert trend.status_code == 200
    assert trend.json()["metric"] == "incidents"


@pytest.mark.anyio
async def test_search_over_projection_index(async_client, sessionmaker, data_factory, make_auth_headers):
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

    headers = await make_auth_headers(RoleEnum.ADMIN)
    response = await async_client.get("/api/v1/search", params={"q": "Иван", "entity_types": "person"}, headers={**headers, "X-Tenant": "test"})
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
    r1 = await async_client.post("/api/v1/exports", json=body, headers={**headers, "X-Tenant": "test"})
    assert r1.status_code == 201
    r2 = await async_client.post("/api/v1/exports", json=body, headers={**headers, "X-Tenant": "test"})
    assert r2.status_code == 201
    assert r1.json()["id"] == r2.json()["id"]

    details = await async_client.get(f"/api/v1/exports/{r1.json()['id']}", headers={"X-Tenant": "test"})
    assert details.status_code == 200


@pytest.mark.anyio
async def test_client_portal_internal_requests_patch(async_client, sessionmaker, data_factory, make_auth_headers):
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

    employee_headers = await make_auth_headers(RoleEnum.EMPLOYEE)

    created = await async_client.post(
        "/api/v1/client-portal/requests",
        json={"title": "Need update", "body": "Please refresh package"},
        headers=employee_headers,
    )
    assert created.status_code == 201
    req_id = created.json()["id"]
    patched = await async_client.patch(
        f"/api/v1/portal-requests/{req_id}",
        json={"status": "in_progress"},
        headers=employee_headers,
    )
    assert patched.status_code == 200
    assert patched.json()["status"] == "in_progress"


@pytest.mark.anyio
async def test_client_user_cannot_patch_internal_portal_requests(async_client, make_auth_headers):
    employee_headers = await make_auth_headers(RoleEnum.EMPLOYEE)
    create_response = await async_client.post(
        "/api/v1/client-portal/requests",
        json={"title": "Need update", "body": "Please refresh package"},
        headers=employee_headers,
    )
    assert create_response.status_code == 201
    req_id = create_response.json()["id"]

    client_headers = await make_auth_headers(RoleEnum.CLIENT_USER)
    patch_response = await async_client.patch(
        f"/api/v1/portal-requests/{req_id}",
        json={"status": "in_progress"},
        headers=client_headers,
    )

    assert patch_response.status_code == 403


@pytest.mark.anyio
async def test_search_returns_extended_facets(async_client, sessionmaker, data_factory, make_auth_headers):
    async with sessionmaker() as session:  # type: AsyncSession
        tenant = await data_factory.ensure_tenant(session=session)
        session.add_all([
            SearchIndexEntry(
                tenant_id=tenant.id,
                entity_type="incident",
                entity_id="incident-1",
                title="Near miss",
                status="reported",
                tags_json={"company_id": "company-1", "site_id": "site-1"},
                route="/incidents/incident-1",
                search_text="Near miss reported",
            ),
            SearchIndexEntry(
                tenant_id=tenant.id,
                entity_type="incident",
                entity_id="incident-2",
                title="Another miss",
                status="closed",
                tags_json={"company_id": "company-1", "site_id": "site-2"},
                route="/incidents/incident-2",
                search_text="Another miss closed",
            ),
        ])
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN)
    response = await async_client.get("/api/v1/search", params={"q": "miss", "entity_types": "incident"}, headers={**headers, "X-Tenant": "test"})
    assert response.status_code == 200
    facets = response.json()["facets"]
    assert facets["status_counts"]["reported"] == 1
    assert facets["company_counts"]["company-1"] == 2
    assert facets["site_counts"]["site-1"] == 1


@pytest.mark.anyio
async def test_analytics_extended_dashboards(async_client, sessionmaker, data_factory, make_auth_headers):
    async with sessionmaker() as session:  # type: AsyncSession
        tenant = await data_factory.ensure_tenant(session=session)
        session.add(PackageReadModel(tenant_id=tenant.id, package_id="pkg-analytics", status="in_progress"))
        await session.commit()

    for endpoint in [
        "/api/v1/analytics/dashboard/incidents",
        "/api/v1/analytics/dashboard/inspections",
        "/api/v1/analytics/dashboard/prescriptions",
        "/api/v1/analytics/dashboard/overdue",
        "/api/v1/analytics/dashboard/sla-load",
        "/api/v1/analytics/dashboard/edo",
    ]:
        headers = await make_auth_headers(RoleEnum.ADMIN)
        response = await async_client.get(endpoint, headers={**headers, "X-Tenant": "test"})
        assert response.status_code == 200
        assert "widgets" in response.json()
