"""HTTP cache (ETag / If-None-Match) contract for /api/v1/{incidents,inspections}
(Phase 9.2 closure / vNext-PERF-03, Session 49).

Closes the "all main list endpoints carry ETag" coverage goal:
companies / sites / documents / tasks (S47) + persons (S48) + incidents +
inspections (S49) = 7/7. Pattern mirrors prior cache-contract files
(`tests/api/test_http_cache_etag_contract.py`, `test_persons_cache_etag_contract.py`).

Both endpoints expose richer filter sets than the simpler companies list,
so cache-key isolation tests are richer too — filter combinations
(`status_filter`, `incident_type` / `inspection_type`, `responsible_id`)
all participate in the ETag hash.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from fastapi import status
from httpx import AsyncClient

from app.models.models import (
    IncidentSeverity,
    IncidentStatus,
    IncidentType,
    InspectionStatus,
    InspectionType,
    RoleEnum,
)
from tests.utils.factories import TestDataFactory

# =============================================================================
# Helpers
# =============================================================================


async def _seed_incident_via_api(
    async_client: AsyncClient,
    headers: dict,
    *,
    company_id: str,
    site_id: str,
    title: str = "Падение груза",
    incident_type: IncidentType = IncidentType.ACCIDENT,
    severity: IncidentSeverity = IncidentSeverity.MEDIUM,
) -> dict:
    """Create an incident through the public API (exercises real write path)."""
    payload = {
        "title": title,
        "incident_type": incident_type.value,
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "company_id": company_id,
        "site_id": site_id,
        "severity": severity.value,
    }
    response = await async_client.post("/api/v1/incidents", json=payload, headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


async def _seed_inspection_via_api(
    async_client: AsyncClient,
    headers: dict,
    *,
    company_id: str,
    site_id: str | None = None,
    authority: str = "ГИТ",
    purpose: str = "Плановая",
    inspection_type: InspectionType = InspectionType.INTERNAL,
) -> dict:
    payload = {
        "company_id": company_id,
        "authority": authority,
        "purpose": purpose,
        "inspection_type": inspection_type.value,
        "scheduled_at": date.today().isoformat(),
    }
    if site_id is not None:
        payload["site_id"] = site_id
    response = await async_client.post("/api/v1/inspections", json=payload, headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


# =============================================================================
# Incidents (/api/v1/incidents)
# =============================================================================


@pytest.mark.asyncio
async def test_incidents_hit_returns_304_with_same_etag(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        site = await data_factory.create_site(
            tenant=tenant, company=company, name="Hit Site", session=session
        )
        await session.commit()
        company_id = str(company.id)
        site_id = str(site.id)

    headers = await make_auth_headers(RoleEnum.ADMIN)
    await _seed_incident_via_api(
        async_client, headers, company_id=company_id, site_id=site_id, title="Hit Incident"
    )

    first = await async_client.get("/api/v1/incidents", headers=headers)
    assert first.status_code == status.HTTP_200_OK
    etag = first.headers["ETag"]

    second = await async_client.get("/api/v1/incidents", headers={**headers, "If-None-Match": etag})
    assert second.status_code == status.HTTP_304_NOT_MODIFIED
    assert second.headers["ETag"] == etag
    assert second.content == b""


@pytest.mark.asyncio
async def test_incidents_miss_with_bogus_etag_returns_200_and_body(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        site = await data_factory.create_site(
            tenant=tenant, company=company, name="Miss Site", session=session
        )
        await session.commit()
        company_id = str(company.id)
        site_id = str(site.id)

    headers = await make_auth_headers(RoleEnum.ADMIN)
    await _seed_incident_via_api(async_client, headers, company_id=company_id, site_id=site_id)

    response = await async_client.get(
        "/api/v1/incidents", headers={**headers, "If-None-Match": '"stale-etag-incidents"'}
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["items"]
    assert response.headers["ETag"] != '"stale-etag-incidents"'


@pytest.mark.asyncio
async def test_incidents_etag_changes_after_create(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    """POST /incidents → ETag changes on next list (write-through invalidation)."""
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        site = await data_factory.create_site(
            tenant=tenant, company=company, name="Create Site", session=session
        )
        await session.commit()
        company_id = str(company.id)
        site_id = str(site.id)

    headers = await make_auth_headers(RoleEnum.ADMIN)
    await _seed_incident_via_api(
        async_client, headers, company_id=company_id, site_id=site_id, title="First Incident"
    )
    first = await async_client.get("/api/v1/incidents", headers=headers)
    initial_etag = first.headers["ETag"]

    await _seed_incident_via_api(
        async_client, headers, company_id=company_id, site_id=site_id, title="Second Incident"
    )

    second = await async_client.get(
        "/api/v1/incidents", headers={**headers, "If-None-Match": initial_etag}
    )
    assert second.status_code == status.HTTP_200_OK
    assert second.headers["ETag"] != initial_etag


@pytest.mark.asyncio
async def test_incidents_etag_changes_after_patch(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    """PATCH /incidents/{id} → ETag changes (updated_at bumps)."""
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        site = await data_factory.create_site(
            tenant=tenant, company=company, name="Patch Site", session=session
        )
        await session.commit()
        company_id = str(company.id)
        site_id = str(site.id)

    headers = await make_auth_headers(RoleEnum.ADMIN)
    incident = await _seed_incident_via_api(
        async_client, headers, company_id=company_id, site_id=site_id
    )
    first = await async_client.get("/api/v1/incidents", headers=headers)
    initial_etag = first.headers["ETag"]

    patch = await async_client.patch(
        f"/api/v1/incidents/{incident['id']}",
        json={"status": IncidentStatus.CLOSED.value},
        headers=headers,
    )
    assert patch.status_code == status.HTTP_200_OK

    second = await async_client.get("/api/v1/incidents", headers=headers)
    assert second.headers["ETag"] != initial_etag


@pytest.mark.asyncio
async def test_incidents_etag_distinct_per_status_filter(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    """``?status_filter=reported`` vs no filter → distinct ETags."""
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        site = await data_factory.create_site(
            tenant=tenant, company=company, name="Filter Site", session=session
        )
        await session.commit()
        company_id = str(company.id)
        site_id = str(site.id)

    headers = await make_auth_headers(RoleEnum.ADMIN)
    await _seed_incident_via_api(async_client, headers, company_id=company_id, site_id=site_id)

    unfiltered = await async_client.get("/api/v1/incidents", headers=headers)
    filtered = await async_client.get(
        f"/api/v1/incidents?status_filter={IncidentStatus.REPORTED.value}", headers=headers
    )
    assert unfiltered.headers["ETag"] != filtered.headers["ETag"]


@pytest.mark.asyncio
async def test_incidents_etag_distinct_per_type_filter(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        site = await data_factory.create_site(
            tenant=tenant, company=company, name="Type Site", session=session
        )
        await session.commit()
        company_id = str(company.id)
        site_id = str(site.id)

    headers = await make_auth_headers(RoleEnum.ADMIN)
    await _seed_incident_via_api(
        async_client,
        headers,
        company_id=company_id,
        site_id=site_id,
        incident_type=IncidentType.ACCIDENT,
    )

    accident = await async_client.get(
        f"/api/v1/incidents?incident_type={IncidentType.ACCIDENT.value}", headers=headers
    )
    near_miss = await async_client.get(
        f"/api/v1/incidents?incident_type={IncidentType.NEAR_MISS.value}", headers=headers
    )
    assert accident.headers["ETag"] != near_miss.headers["ETag"]


@pytest.mark.asyncio
async def test_incidents_empty_list_has_stable_etag(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    """Zero incidents → still valid stable ETag (conditional GET works on empty)."""
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(slug="delta", session=session)
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN, tenant="delta")
    first = await async_client.get("/api/v1/incidents", headers=headers)
    assert first.status_code == status.HTTP_200_OK
    assert first.json()["items"] == []
    etag = first.headers["ETag"]
    assert etag

    second = await async_client.get("/api/v1/incidents", headers={**headers, "If-None-Match": etag})
    assert second.status_code == status.HTTP_304_NOT_MODIFIED


@pytest.mark.asyncio
async def test_incidents_cross_tenant_etag_does_not_leak(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    """Tenant A's ETag in tenant B's request → 200, not 304 (anti-leak)."""
    async with sessionmaker() as session:
        tenant_a = await data_factory.ensure_tenant(slug="acme", session=session)
        tenant_b = await data_factory.ensure_tenant(slug="beta", session=session)
        company_a = await data_factory.create_company(tenant=tenant_a, name="A Co", session=session)
        company_b = await data_factory.create_company(tenant=tenant_b, name="B Co", session=session)
        site_a = await data_factory.create_site(
            tenant=tenant_a, company=company_a, name="A Site", session=session
        )
        site_b = await data_factory.create_site(
            tenant=tenant_b, company=company_b, name="B Site", session=session
        )
        await session.commit()
        company_a_id, site_a_id = str(company_a.id), str(site_a.id)
        company_b_id, site_b_id = str(company_b.id), str(site_b.id)

    headers_a = await make_auth_headers(RoleEnum.ADMIN, tenant="acme")
    headers_b = await make_auth_headers(RoleEnum.ADMIN, tenant="beta")
    await _seed_incident_via_api(
        async_client, headers_a, company_id=company_a_id, site_id=site_a_id
    )
    await _seed_incident_via_api(
        async_client, headers_b, company_id=company_b_id, site_id=site_b_id
    )

    a = await async_client.get("/api/v1/incidents", headers=headers_a)
    etag_a = a.headers["ETag"]

    leaked = await async_client.get(
        "/api/v1/incidents", headers={**headers_b, "If-None-Match": etag_a}
    )
    assert leaked.status_code == status.HTTP_200_OK


@pytest.mark.asyncio
async def test_incidents_etag_deterministic_across_repeated_reads(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        site = await data_factory.create_site(
            tenant=tenant, company=company, name="Det Site", session=session
        )
        await session.commit()
        company_id = str(company.id)
        site_id = str(site.id)

    headers = await make_auth_headers(RoleEnum.ADMIN)
    await _seed_incident_via_api(async_client, headers, company_id=company_id, site_id=site_id)
    etags = [
        (await async_client.get("/api/v1/incidents", headers=headers)).headers["ETag"]
        for _ in range(3)
    ]
    assert etags[0] == etags[1] == etags[2]


# =============================================================================
# Inspections (/api/v1/inspections)
# =============================================================================


@pytest.mark.asyncio
async def test_inspections_hit_returns_304(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        await session.commit()
        company_id = str(company.id)

    headers = await make_auth_headers(RoleEnum.ADMIN)
    await _seed_inspection_via_api(async_client, headers, company_id=company_id)

    first = await async_client.get("/api/v1/inspections", headers=headers)
    assert first.status_code == status.HTTP_200_OK
    etag = first.headers["ETag"]

    second = await async_client.get(
        "/api/v1/inspections", headers={**headers, "If-None-Match": etag}
    )
    assert second.status_code == status.HTTP_304_NOT_MODIFIED
    assert second.content == b""


@pytest.mark.asyncio
async def test_inspections_miss_with_bogus_etag_returns_200(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        await session.commit()
        company_id = str(company.id)

    headers = await make_auth_headers(RoleEnum.ADMIN)
    await _seed_inspection_via_api(async_client, headers, company_id=company_id)

    response = await async_client.get(
        "/api/v1/inspections", headers={**headers, "If-None-Match": '"stale"'}
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["items"]


@pytest.mark.asyncio
async def test_inspections_etag_changes_after_create(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        await session.commit()
        company_id = str(company.id)

    headers = await make_auth_headers(RoleEnum.ADMIN)
    await _seed_inspection_via_api(async_client, headers, company_id=company_id, authority="ГИТ")
    first = await async_client.get("/api/v1/inspections", headers=headers)
    initial_etag = first.headers["ETag"]

    await _seed_inspection_via_api(
        async_client, headers, company_id=company_id, authority="Роспотребнадзор"
    )

    second = await async_client.get("/api/v1/inspections", headers=headers)
    assert second.headers["ETag"] != initial_etag


@pytest.mark.asyncio
async def test_inspections_etag_changes_after_patch(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        await session.commit()
        company_id = str(company.id)

    headers = await make_auth_headers(RoleEnum.ADMIN)
    inspection = await _seed_inspection_via_api(async_client, headers, company_id=company_id)
    first = await async_client.get("/api/v1/inspections", headers=headers)
    initial_etag = first.headers["ETag"]

    patch = await async_client.patch(
        f"/api/v1/inspections/{inspection['id']}",
        json={"status": InspectionStatus.IN_PROGRESS.value},
        headers=headers,
    )
    assert patch.status_code == status.HTTP_200_OK

    second = await async_client.get("/api/v1/inspections", headers=headers)
    assert second.headers["ETag"] != initial_etag


@pytest.mark.asyncio
async def test_inspections_etag_distinct_per_status_filter(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        await session.commit()
        company_id = str(company.id)

    headers = await make_auth_headers(RoleEnum.ADMIN)
    await _seed_inspection_via_api(async_client, headers, company_id=company_id)

    unfiltered = await async_client.get("/api/v1/inspections", headers=headers)
    planned = await async_client.get(
        f"/api/v1/inspections?status_filter={InspectionStatus.PLANNED.value}", headers=headers
    )
    assert unfiltered.headers["ETag"] != planned.headers["ETag"]


@pytest.mark.asyncio
async def test_inspections_etag_distinct_per_type_filter(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        await session.commit()
        company_id = str(company.id)

    headers = await make_auth_headers(RoleEnum.ADMIN)
    await _seed_inspection_via_api(
        async_client, headers, company_id=company_id, inspection_type=InspectionType.INTERNAL
    )

    internal = await async_client.get(
        f"/api/v1/inspections?inspection_type={InspectionType.INTERNAL.value}", headers=headers
    )
    external = await async_client.get(
        f"/api/v1/inspections?inspection_type={InspectionType.EXTERNAL.value}", headers=headers
    )
    assert internal.headers["ETag"] != external.headers["ETag"]


@pytest.mark.asyncio
async def test_inspections_empty_list_has_stable_etag(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(slug="gamma", session=session)
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN, tenant="gamma")
    first = await async_client.get("/api/v1/inspections", headers=headers)
    assert first.status_code == status.HTTP_200_OK
    assert first.json()["items"] == []
    etag = first.headers["ETag"]
    assert etag

    second = await async_client.get(
        "/api/v1/inspections", headers={**headers, "If-None-Match": etag}
    )
    assert second.status_code == status.HTTP_304_NOT_MODIFIED


@pytest.mark.asyncio
async def test_inspections_cross_tenant_etag_does_not_leak(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        tenant_a = await data_factory.ensure_tenant(slug="acme", session=session)
        tenant_b = await data_factory.ensure_tenant(slug="beta", session=session)
        company_a = await data_factory.create_company(tenant=tenant_a, name="A Co", session=session)
        company_b = await data_factory.create_company(tenant=tenant_b, name="B Co", session=session)
        await session.commit()
        company_a_id = str(company_a.id)
        company_b_id = str(company_b.id)

    headers_a = await make_auth_headers(RoleEnum.ADMIN, tenant="acme")
    headers_b = await make_auth_headers(RoleEnum.ADMIN, tenant="beta")
    await _seed_inspection_via_api(async_client, headers_a, company_id=company_a_id)
    await _seed_inspection_via_api(async_client, headers_b, company_id=company_b_id)

    a = await async_client.get("/api/v1/inspections", headers=headers_a)
    etag_a = a.headers["ETag"]

    leaked = await async_client.get(
        "/api/v1/inspections", headers={**headers_b, "If-None-Match": etag_a}
    )
    assert leaked.status_code == status.HTTP_200_OK


@pytest.mark.asyncio
async def test_inspections_etag_distinct_per_page(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        await session.commit()
        company_id = str(company.id)

    headers = await make_auth_headers(RoleEnum.ADMIN)
    for i in range(4):
        await _seed_inspection_via_api(
            async_client, headers, company_id=company_id, authority=f"Authority {i}"
        )

    page_a = await async_client.get("/api/v1/inspections?limit=2&offset=0", headers=headers)
    page_b = await async_client.get("/api/v1/inspections?limit=2&offset=2", headers=headers)
    assert page_a.headers["ETag"] != page_b.headers["ETag"]


@pytest.mark.asyncio
async def test_inspections_etag_quoted_and_deterministic(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    """RFC 7232 quoted format + 3-repeat determinism in one test."""
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        await session.commit()
        company_id = str(company.id)

    headers = await make_auth_headers(RoleEnum.ADMIN)
    await _seed_inspection_via_api(async_client, headers, company_id=company_id)

    etags = []
    for _ in range(3):
        response = await async_client.get("/api/v1/inspections", headers=headers)
        etag = response.headers["ETag"]
        assert etag.startswith('"') and etag.endswith('"'), f"ETag not quoted: {etag!r}"
        etags.append(etag)
    assert etags[0] == etags[1] == etags[2]
