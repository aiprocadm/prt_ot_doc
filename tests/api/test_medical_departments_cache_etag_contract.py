"""HTTP cache (ETag / If-None-Match) contract for /api/v1/medical/exams + /api/v1/departments
(Phase 9.2 extension / vNext-PERF-03, Session 53).

Continues the rollout. Two endpoints: ``/medical/exams`` (pagination + person/
status filters; no API POST — seeding via ORM) and ``/departments`` (pagination
+ company filter; full API POST). After S53, 16 list endpoints carry ETag
conditional-GET.

Pinned axes: hit/miss/mutation invalidation/filter isolation/empty-stable/
cross-tenant anti-leak (for departments — sensitive org structure).
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi import status
from httpx import AsyncClient

from app.models.models import MedicalExam, RoleEnum
from tests.utils.factories import TestDataFactory


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------


async def _seed_medical_exam(
    session,
    *,
    tenant_id: str,
    person_id: str,
    exam_type: str = "periodic",
    days_until_valid: int = 30,
    conclusion: str = "fit",
) -> MedicalExam:
    """Seed a MedicalExam through ORM (no public API POST endpoint)."""
    today = date.today()
    exam = MedicalExam(
        tenant_id=tenant_id,
        person_id=person_id,
        exam_type=exam_type,
        exam_date=today - timedelta(days=10),
        valid_until=today + timedelta(days=days_until_valid),
        conclusion=conclusion,
    )
    session.add(exam)
    await session.flush()
    return exam


async def _seed_department(
    async_client: AsyncClient,
    headers: dict,
    *,
    company_id: str,
    name: str = "Производственный отдел",
    code: str | None = None,
) -> dict:
    payload: dict = {"company_id": company_id, "name": name}
    if code is not None:
        payload["code"] = code
    response = await async_client.post("/api/v1/departments", json=payload, headers=headers)
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


# =============================================================================
# /api/v1/medical/exams
# =============================================================================


@pytest.mark.asyncio
async def test_medical_exams_hit_returns_304(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        person = await data_factory.create_person(
            tenant=tenant, company=company, first_name="Med", last_name="Patient", session=session
        )
        await _seed_medical_exam(
            session, tenant_id=tenant.id, person_id=person.id
        )
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN)
    first = await async_client.get("/api/v1/medical/exams", headers=headers)
    assert first.status_code == status.HTTP_200_OK
    etag = first.headers["ETag"]

    second = await async_client.get(
        "/api/v1/medical/exams", headers={**headers, "If-None-Match": etag}
    )
    assert second.status_code == status.HTTP_304_NOT_MODIFIED
    assert second.headers["ETag"] == etag
    assert second.content == b""


@pytest.mark.asyncio
async def test_medical_exams_miss_with_bogus_etag(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        person = await data_factory.create_person(
            tenant=tenant, company=company, first_name="Miss", last_name="Test", session=session
        )
        await _seed_medical_exam(session, tenant_id=tenant.id, person_id=person.id)
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN)
    response = await async_client.get(
        "/api/v1/medical/exams", headers={**headers, "If-None-Match": '"stale-medical"'}
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["items"]


@pytest.mark.asyncio
async def test_medical_exams_etag_distinct_per_person_filter(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        person_a = await data_factory.create_person(
            tenant=tenant, company=company, first_name="A", last_name="Med", session=session
        )
        person_b = await data_factory.create_person(
            tenant=tenant, company=company, first_name="B", last_name="Med", session=session
        )
        await _seed_medical_exam(session, tenant_id=tenant.id, person_id=person_a.id)
        await _seed_medical_exam(session, tenant_id=tenant.id, person_id=person_b.id)
        await session.commit()
        person_a_id = str(person_a.id)

    headers = await make_auth_headers(RoleEnum.ADMIN)
    unfiltered = await async_client.get("/api/v1/medical/exams", headers=headers)
    filtered = await async_client.get(
        f"/api/v1/medical/exams?person_id={person_a_id}", headers=headers
    )
    assert unfiltered.headers["ETag"] != filtered.headers["ETag"]


@pytest.mark.asyncio
async def test_medical_exams_etag_distinct_per_status_filter(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    """``?status=expired`` vs ``?status=upcoming`` → distinct ETags."""
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        person = await data_factory.create_person(
            tenant=tenant, company=company, first_name="Status", last_name="F", session=session
        )
        # One upcoming, one expired
        await _seed_medical_exam(session, tenant_id=tenant.id, person_id=person.id, days_until_valid=30)
        await _seed_medical_exam(
            session, tenant_id=tenant.id, person_id=person.id, days_until_valid=-30
        )
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN)
    expired = await async_client.get(
        "/api/v1/medical/exams?status=expired", headers=headers
    )
    upcoming = await async_client.get(
        "/api/v1/medical/exams?status=upcoming", headers=headers
    )
    assert expired.headers["ETag"] != upcoming.headers["ETag"]


@pytest.mark.asyncio
async def test_medical_exams_empty_list_stable_etag(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(slug="delta", session=session)
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN, tenant="delta")
    first = await async_client.get("/api/v1/medical/exams", headers=headers)
    assert first.status_code == status.HTTP_200_OK
    assert first.json()["items"] == []
    etag = first.headers["ETag"]
    assert etag

    second = await async_client.get(
        "/api/v1/medical/exams", headers={**headers, "If-None-Match": etag}
    )
    assert second.status_code == status.HTTP_304_NOT_MODIFIED


# =============================================================================
# /api/v1/departments
# =============================================================================


@pytest.mark.asyncio
async def test_departments_hit_returns_304(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        await session.commit()
        company_id = str(company.id)

    headers = await make_auth_headers(RoleEnum.ADMIN)
    await _seed_department(async_client, headers, company_id=company_id, name="Hit Dept")

    first = await async_client.get("/api/v1/departments", headers=headers)
    assert first.status_code == status.HTTP_200_OK
    etag = first.headers["ETag"]

    second = await async_client.get(
        "/api/v1/departments", headers={**headers, "If-None-Match": etag}
    )
    assert second.status_code == status.HTTP_304_NOT_MODIFIED
    assert second.content == b""


@pytest.mark.asyncio
async def test_departments_miss_with_bogus_etag(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        await session.commit()
        company_id = str(company.id)

    headers = await make_auth_headers(RoleEnum.ADMIN)
    await _seed_department(async_client, headers, company_id=company_id, name="Miss Dept")

    response = await async_client.get(
        "/api/v1/departments", headers={**headers, "If-None-Match": '"stale-dept"'}
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["items"]


@pytest.mark.asyncio
async def test_departments_etag_changes_after_create(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        await session.commit()
        company_id = str(company.id)

    headers = await make_auth_headers(RoleEnum.ADMIN)
    await _seed_department(async_client, headers, company_id=company_id, name="Before-POST")
    first = await async_client.get("/api/v1/departments", headers=headers)
    initial_etag = first.headers["ETag"]

    await _seed_department(async_client, headers, company_id=company_id, name="After-POST")

    second = await async_client.get("/api/v1/departments", headers=headers)
    assert second.headers["ETag"] != initial_etag


@pytest.mark.asyncio
async def test_departments_etag_distinct_per_company_filter(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company_a = await data_factory.create_company(tenant=tenant, name="A Co", session=session)
        company_b = await data_factory.create_company(tenant=tenant, name="B Co", session=session)
        await session.commit()
        company_a_id, company_b_id = str(company_a.id), str(company_b.id)

    headers = await make_auth_headers(RoleEnum.ADMIN)
    await _seed_department(async_client, headers, company_id=company_a_id, name="Dept A")
    await _seed_department(async_client, headers, company_id=company_b_id, name="Dept B")

    unfiltered = await async_client.get("/api/v1/departments", headers=headers)
    filtered_a = await async_client.get(
        f"/api/v1/departments?company_id={company_a_id}", headers=headers
    )
    assert unfiltered.headers["ETag"] != filtered_a.headers["ETag"]


@pytest.mark.asyncio
async def test_departments_etag_distinct_per_page(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        await session.commit()
        company_id = str(company.id)

    headers = await make_auth_headers(RoleEnum.ADMIN)
    for i in range(4):
        await _seed_department(
            async_client, headers, company_id=company_id, name=f"Page Dept {i}"
        )

    a = await async_client.get("/api/v1/departments?limit=2&offset=0", headers=headers)
    b = await async_client.get("/api/v1/departments?limit=2&offset=2", headers=headers)
    assert a.headers["ETag"] != b.headers["ETag"]


@pytest.mark.asyncio
async def test_departments_empty_list_stable_etag(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(slug="gamma", session=session)
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN, tenant="gamma")
    first = await async_client.get("/api/v1/departments", headers=headers)
    assert first.status_code == status.HTTP_200_OK
    assert first.json()["items"] == []
    etag = first.headers["ETag"]
    assert etag

    second = await async_client.get(
        "/api/v1/departments", headers={**headers, "If-None-Match": etag}
    )
    assert second.status_code == status.HTTP_304_NOT_MODIFIED


@pytest.mark.asyncio
async def test_departments_cross_tenant_etag_does_not_leak(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    """Departments contain org structure — cross-tenant leak would expose it."""
    async with sessionmaker() as session:
        tenant_a = await data_factory.ensure_tenant(slug="acme", session=session)
        tenant_b = await data_factory.ensure_tenant(slug="beta", session=session)
        company_a = await data_factory.create_company(tenant=tenant_a, name="A Co", session=session)
        company_b = await data_factory.create_company(tenant=tenant_b, name="B Co", session=session)
        await session.commit()
        company_a_id, company_b_id = str(company_a.id), str(company_b.id)

    headers_a = await make_auth_headers(RoleEnum.ADMIN, tenant="acme")
    headers_b = await make_auth_headers(RoleEnum.ADMIN, tenant="beta")
    await _seed_department(async_client, headers_a, company_id=company_a_id, name="Same Name")
    await _seed_department(async_client, headers_b, company_id=company_b_id, name="Same Name")

    a = await async_client.get("/api/v1/departments", headers=headers_a)
    etag_a = a.headers["ETag"]

    leaked = await async_client.get(
        "/api/v1/departments", headers={**headers_b, "If-None-Match": etag_a}
    )
    assert leaked.status_code == status.HTTP_200_OK


@pytest.mark.asyncio
async def test_departments_etag_deterministic(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        await session.commit()
        company_id = str(company.id)

    headers = await make_auth_headers(RoleEnum.ADMIN)
    await _seed_department(async_client, headers, company_id=company_id, name="Stable")
    etags = []
    for _ in range(3):
        response = await async_client.get("/api/v1/departments", headers=headers)
        etags.append(response.headers["ETag"])
    assert etags[0] == etags[1] == etags[2]
