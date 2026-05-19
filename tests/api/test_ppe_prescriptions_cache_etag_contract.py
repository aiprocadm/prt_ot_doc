"""HTTP cache (ETag / If-None-Match) contract for /api/v1/ppe/{items,issues} and /api/v1/prescriptions
(Phase 9.2 extension / vNext-PERF-03, Session 51).

Continues the ETag rollout to additional list endpoints, leveraging the
shared ``compute_list_etag`` helper consolidated in Session 50. Three
endpoints in one file because they share the same contract pattern and
seeding goes through the existing API surface:

- ``/api/v1/ppe/items`` — simple pagination (limit/offset).
- ``/api/v1/ppe/issues`` — pagination + ``person_id`` and ``active_only`` filters.
- ``/api/v1/prescriptions`` — pagination + 4 filter axes (inspection_id,
  incident_id, status, assignee_id).

Pinned axes per endpoint: hit/miss/POST-invalidation/PATCH-invalidation/
filter-distinct/empty-stable/cross-tenant-anti-leak. After S51, 10 of the
project's main list endpoints carry ETag conditional-GET (companies,
sites, documents, tasks, persons, incidents, inspections, ppe/items,
ppe/issues, prescriptions).
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import select

from app.models.models import (
    PrescriptionStatus,
    RoleEnum,
)
from app.schemas.ppe import PPEItemCategory
from tests.utils.factories import TestDataFactory


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------


async def _seed_ppe_item(
    async_client: AsyncClient,
    headers: dict,
    *,
    name: str = "Каска защитная",
    code: str | None = None,
    category: PPEItemCategory = PPEItemCategory.HEAD,
) -> dict:
    payload = {"name": name, "category": category.value}
    if code is not None:
        payload["code"] = code
    response = await async_client.post("/api/v1/ppe/items", json=payload, headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


async def _seed_ppe_issue(
    async_client: AsyncClient,
    headers: dict,
    *,
    person_id: str,
    item_id: str,
    quantity: int = 1,
) -> dict:
    payload = {"person_id": person_id, "item_id": item_id, "quantity": quantity}
    response = await async_client.post("/api/v1/ppe/issues", json=payload, headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


async def _seed_inspection(
    async_client: AsyncClient,
    headers: dict,
    *,
    company_id: str,
    site_id: str | None = None,
    authority: str = "Ростехнадзор",
) -> str:
    payload = {
        "company_id": company_id,
        "authority": authority,
        "scheduled_at": date.today().isoformat(),
    }
    if site_id is not None:
        payload["site_id"] = site_id
    response = await async_client.post("/api/v1/inspections", json=payload, headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()["id"]


async def _seed_prescription(
    async_client: AsyncClient,
    headers: dict,
    *,
    inspection_id: str,
    description: str = "Provide corrective action plan",
) -> dict:
    payload = {
        "inspection_id": inspection_id,
        "description": description,
        "due_at": date.today().isoformat(),
    }
    response = await async_client.post("/api/v1/prescriptions", json=payload, headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


# =============================================================================
# /api/v1/ppe/items
# =============================================================================


@pytest.mark.asyncio
async def test_ppe_items_hit_returns_304(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN)
    await _seed_ppe_item(async_client, headers, name="Hit Item")

    first = await async_client.get("/api/v1/ppe/items", headers=headers)
    assert first.status_code == status.HTTP_200_OK
    etag = first.headers["ETag"]

    second = await async_client.get(
        "/api/v1/ppe/items", headers={**headers, "If-None-Match": etag}
    )
    assert second.status_code == status.HTTP_304_NOT_MODIFIED
    assert second.headers["ETag"] == etag
    assert second.content == b""


@pytest.mark.asyncio
async def test_ppe_items_miss_with_bogus_etag(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN)
    await _seed_ppe_item(async_client, headers)

    response = await async_client.get(
        "/api/v1/ppe/items", headers={**headers, "If-None-Match": '"stale-ppe"'}
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["items"]


@pytest.mark.asyncio
async def test_ppe_items_etag_changes_after_create(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN)
    await _seed_ppe_item(async_client, headers, name="Before")
    first = await async_client.get("/api/v1/ppe/items", headers=headers)
    initial_etag = first.headers["ETag"]

    await _seed_ppe_item(async_client, headers, name="After")

    second = await async_client.get("/api/v1/ppe/items", headers=headers)
    assert second.headers["ETag"] != initial_etag


@pytest.mark.asyncio
async def test_ppe_items_etag_distinct_per_page(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN)
    for i in range(4):
        await _seed_ppe_item(async_client, headers, name=f"Item {i}")

    a = await async_client.get("/api/v1/ppe/items?limit=2&offset=0", headers=headers)
    b = await async_client.get("/api/v1/ppe/items?limit=2&offset=2", headers=headers)
    assert a.headers["ETag"] != b.headers["ETag"]


@pytest.mark.asyncio
async def test_ppe_items_empty_list_stable_etag(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(slug="delta", session=session)
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN, tenant="delta")
    first = await async_client.get("/api/v1/ppe/items", headers=headers)
    assert first.status_code == status.HTTP_200_OK
    assert first.json()["items"] == []
    etag = first.headers["ETag"]
    assert etag

    second = await async_client.get(
        "/api/v1/ppe/items", headers={**headers, "If-None-Match": etag}
    )
    assert second.status_code == status.HTTP_304_NOT_MODIFIED


# =============================================================================
# /api/v1/ppe/issues
# =============================================================================


@pytest.mark.asyncio
async def test_ppe_issues_hit_returns_304(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        person = await data_factory.create_person(
            tenant=tenant, company=company, first_name="Issue", last_name="Recipient", session=session
        )
        await session.commit()
        person_id = str(person.id)

    headers = await make_auth_headers(RoleEnum.ADMIN)
    item = await _seed_ppe_item(async_client, headers, name="Hard Hat")
    await _seed_ppe_issue(async_client, headers, person_id=person_id, item_id=item["id"])

    first = await async_client.get("/api/v1/ppe/issues", headers=headers)
    assert first.status_code == status.HTTP_200_OK
    etag = first.headers["ETag"]

    second = await async_client.get(
        "/api/v1/ppe/issues", headers={**headers, "If-None-Match": etag}
    )
    assert second.status_code == status.HTTP_304_NOT_MODIFIED


@pytest.mark.asyncio
async def test_ppe_issues_etag_distinct_per_person_filter(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    """``?person_id=`` participates in cache key (no collisions on filter)."""
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        person = await data_factory.create_person(
            tenant=tenant, company=company, first_name="P1", last_name="F", session=session
        )
        await session.commit()
        person_id = str(person.id)

    headers = await make_auth_headers(RoleEnum.ADMIN)
    item = await _seed_ppe_item(async_client, headers, name="Filter Test")
    await _seed_ppe_issue(async_client, headers, person_id=person_id, item_id=item["id"])

    unfiltered = await async_client.get("/api/v1/ppe/issues", headers=headers)
    filtered = await async_client.get(
        f"/api/v1/ppe/issues?person_id={person_id}", headers=headers
    )
    assert unfiltered.headers["ETag"] != filtered.headers["ETag"]


@pytest.mark.asyncio
async def test_ppe_issues_etag_distinct_per_active_only_flag(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    """Boolean ``?active_only=`` flag in cache key — true vs false → distinct ETags."""
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        person = await data_factory.create_person(
            tenant=tenant, company=company, first_name="A", last_name="O", session=session
        )
        await session.commit()
        person_id = str(person.id)

    headers = await make_auth_headers(RoleEnum.ADMIN)
    item = await _seed_ppe_item(async_client, headers, name="Active Filter")
    await _seed_ppe_issue(async_client, headers, person_id=person_id, item_id=item["id"])

    all_issues = await async_client.get("/api/v1/ppe/issues", headers=headers)
    active_only = await async_client.get(
        "/api/v1/ppe/issues?active_only=true", headers=headers
    )
    assert all_issues.headers["ETag"] != active_only.headers["ETag"]


@pytest.mark.asyncio
async def test_ppe_issues_etag_changes_after_create(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        person = await data_factory.create_person(
            tenant=tenant, company=company, first_name="Bumper", last_name="Test", session=session
        )
        await session.commit()
        person_id = str(person.id)

    headers = await make_auth_headers(RoleEnum.ADMIN)
    item = await _seed_ppe_item(async_client, headers, name="Bump Item")
    await _seed_ppe_issue(async_client, headers, person_id=person_id, item_id=item["id"])
    first = await async_client.get("/api/v1/ppe/issues", headers=headers)
    initial_etag = first.headers["ETag"]

    await _seed_ppe_issue(async_client, headers, person_id=person_id, item_id=item["id"])

    second = await async_client.get("/api/v1/ppe/issues", headers=headers)
    assert second.headers["ETag"] != initial_etag


@pytest.mark.asyncio
async def test_ppe_issues_empty_list_stable_etag(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(slug="gamma", session=session)
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN, tenant="gamma")
    first = await async_client.get("/api/v1/ppe/issues", headers=headers)
    assert first.status_code == status.HTTP_200_OK
    assert first.json()["items"] == []
    etag = first.headers["ETag"]
    assert etag

    second = await async_client.get(
        "/api/v1/ppe/issues", headers={**headers, "If-None-Match": etag}
    )
    assert second.status_code == status.HTTP_304_NOT_MODIFIED


# =============================================================================
# /api/v1/prescriptions
# =============================================================================


@pytest.mark.asyncio
async def test_prescriptions_hit_returns_304(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        site = await data_factory.create_site(
            tenant=tenant, company=company, name="P Site", session=session
        )
        await session.commit()
        company_id, site_id = str(company.id), str(site.id)

    headers = await make_auth_headers(RoleEnum.ADMIN)
    inspection_id = await _seed_inspection(
        async_client, headers, company_id=company_id, site_id=site_id
    )
    await _seed_prescription(async_client, headers, inspection_id=inspection_id)

    first = await async_client.get("/api/v1/prescriptions", headers=headers)
    assert first.status_code == status.HTTP_200_OK
    etag = first.headers["ETag"]

    second = await async_client.get(
        "/api/v1/prescriptions", headers={**headers, "If-None-Match": etag}
    )
    assert second.status_code == status.HTTP_304_NOT_MODIFIED
    assert second.content == b""


@pytest.mark.asyncio
async def test_prescriptions_etag_changes_after_patch(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        site = await data_factory.create_site(
            tenant=tenant, company=company, name="Patch P Site", session=session
        )
        await session.commit()
        company_id, site_id = str(company.id), str(site.id)

    headers = await make_auth_headers(RoleEnum.ADMIN)
    inspection_id = await _seed_inspection(
        async_client, headers, company_id=company_id, site_id=site_id
    )
    prescription = await _seed_prescription(async_client, headers, inspection_id=inspection_id)
    first = await async_client.get("/api/v1/prescriptions", headers=headers)
    initial_etag = first.headers["ETag"]

    patch = await async_client.patch(
        f"/api/v1/prescriptions/{prescription['id']}",
        json={"status": PrescriptionStatus.COMPLETED.value},
        headers=headers,
    )
    assert patch.status_code == status.HTTP_200_OK

    second = await async_client.get("/api/v1/prescriptions", headers=headers)
    assert second.headers["ETag"] != initial_etag


@pytest.mark.asyncio
async def test_prescriptions_etag_distinct_per_inspection_filter(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        site = await data_factory.create_site(
            tenant=tenant, company=company, name="IF Site", session=session
        )
        await session.commit()
        company_id, site_id = str(company.id), str(site.id)

    headers = await make_auth_headers(RoleEnum.ADMIN)
    inspection_id = await _seed_inspection(
        async_client, headers, company_id=company_id, site_id=site_id
    )
    await _seed_prescription(async_client, headers, inspection_id=inspection_id)

    unfiltered = await async_client.get("/api/v1/prescriptions", headers=headers)
    filtered = await async_client.get(
        f"/api/v1/prescriptions?inspection_id={inspection_id}", headers=headers
    )
    assert unfiltered.headers["ETag"] != filtered.headers["ETag"]


@pytest.mark.asyncio
async def test_prescriptions_etag_distinct_per_status_filter(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        site = await data_factory.create_site(
            tenant=tenant, company=company, name="StatusF Site", session=session
        )
        await session.commit()
        company_id, site_id = str(company.id), str(site.id)

    headers = await make_auth_headers(RoleEnum.ADMIN)
    inspection_id = await _seed_inspection(
        async_client, headers, company_id=company_id, site_id=site_id
    )
    await _seed_prescription(async_client, headers, inspection_id=inspection_id)

    open_status = await async_client.get(
        f"/api/v1/prescriptions?status={PrescriptionStatus.OPEN.value}", headers=headers
    )
    completed_status = await async_client.get(
        f"/api/v1/prescriptions?status={PrescriptionStatus.COMPLETED.value}", headers=headers
    )
    assert open_status.headers["ETag"] != completed_status.headers["ETag"]


@pytest.mark.asyncio
async def test_prescriptions_empty_list_stable_etag(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(slug="epsilon", session=session)
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN, tenant="epsilon")
    first = await async_client.get("/api/v1/prescriptions", headers=headers)
    assert first.status_code == status.HTTP_200_OK
    assert first.json()["items"] == []
    etag = first.headers["ETag"]
    assert etag

    second = await async_client.get(
        "/api/v1/prescriptions", headers={**headers, "If-None-Match": etag}
    )
    assert second.status_code == status.HTTP_304_NOT_MODIFIED


@pytest.mark.asyncio
async def test_prescriptions_cross_tenant_etag_does_not_leak(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    """Tenant A's prescriptions ETag in tenant B request → 200 (anti-leak guard)."""
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
    insp_a = await _seed_inspection(
        async_client, headers_a, company_id=company_a_id, site_id=site_a_id
    )
    insp_b = await _seed_inspection(
        async_client, headers_b, company_id=company_b_id, site_id=site_b_id
    )
    await _seed_prescription(async_client, headers_a, inspection_id=insp_a)
    await _seed_prescription(async_client, headers_b, inspection_id=insp_b)

    a = await async_client.get("/api/v1/prescriptions", headers=headers_a)
    etag_a = a.headers["ETag"]

    leaked = await async_client.get(
        "/api/v1/prescriptions", headers={**headers_b, "If-None-Match": etag_a}
    )
    assert leaked.status_code == status.HTTP_200_OK
