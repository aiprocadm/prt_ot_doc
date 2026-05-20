"""HTTP cache (ETag / If-None-Match) contract for /api/v1/contractors/registry +
/api/v1/journals (Phase 9.2 extension / vNext-PERF-03, Session 55).

Continues the rollout. Two endpoints: ``/contractors/registry`` (pagination +
per-user contractor_ids/roles in cache key — high-traffic external-party list)
and ``/journals`` (pagination + company filter — safety instruction journals).
Both have public API POST endpoints, so mutation-invalidation is verified end
to end.

After S55, coverage extends from 16 → 18+ list endpoints carrying ETag
conditional-GET.

Pinned axes: hit/miss/mutation invalidation/filter isolation/empty-stable.
"""

from __future__ import annotations

from datetime import date

import pytest
from fastapi import status
from httpx import AsyncClient

from app.models.models import RoleEnum
from tests.utils.factories import TestDataFactory


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------


async def _seed_contractor(
    async_client: AsyncClient,
    headers: dict,
    *,
    name: str = "Acme Contracting",
    inn: str | None = None,
) -> dict:
    payload: dict = {"name": name}
    if inn is not None:
        payload["inn"] = inn
    response = await async_client.post(
        "/api/v1/contractors/registry", json=payload, headers=headers
    )
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


async def _seed_journal(
    async_client: AsyncClient,
    headers: dict,
    *,
    company_id: str | None = None,
    title: str = "Safety Briefings 2026",
    journal_type: str = "primary",
) -> dict:
    payload: dict = {
        "company_id": company_id,
        "title": title,
        "journal_type": journal_type,
        "started_at": date.today().isoformat(),
    }
    response = await async_client.post(
        "/api/v1/journals", json=payload, headers=headers
    )
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


# =============================================================================
# /api/v1/contractors/registry
# =============================================================================


@pytest.mark.asyncio
async def test_contractors_registry_hit_returns_304(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN)
    await _seed_contractor(async_client, headers, name="Hit Contractor")

    first = await async_client.get("/api/v1/contractors/registry", headers=headers)
    assert first.status_code == status.HTTP_200_OK
    etag = first.headers["ETag"]

    second = await async_client.get(
        "/api/v1/contractors/registry", headers={**headers, "If-None-Match": etag}
    )
    assert second.status_code == status.HTTP_304_NOT_MODIFIED
    assert second.headers["ETag"] == etag
    assert second.content == b""


@pytest.mark.asyncio
async def test_contractors_registry_miss_with_bogus_etag(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN)
    await _seed_contractor(async_client, headers, name="Miss Contractor")

    response = await async_client.get(
        "/api/v1/contractors/registry",
        headers={**headers, "If-None-Match": '"stale-contractor"'},
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["items"]


@pytest.mark.asyncio
async def test_contractors_registry_etag_changes_after_create(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN)
    await _seed_contractor(async_client, headers, name="Before POST")
    first = await async_client.get("/api/v1/contractors/registry", headers=headers)
    initial_etag = first.headers["ETag"]

    await _seed_contractor(async_client, headers, name="After POST")

    second = await async_client.get("/api/v1/contractors/registry", headers=headers)
    assert second.headers["ETag"] != initial_etag


@pytest.mark.asyncio
async def test_contractors_registry_etag_distinct_per_page(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN)
    for i in range(4):
        await _seed_contractor(async_client, headers, name=f"Page Contractor {i}")

    a = await async_client.get(
        "/api/v1/contractors/registry?limit=2&offset=0", headers=headers
    )
    b = await async_client.get(
        "/api/v1/contractors/registry?limit=2&offset=2", headers=headers
    )
    assert a.headers["ETag"] != b.headers["ETag"]


@pytest.mark.asyncio
async def test_contractors_registry_empty_list_stable_etag(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(slug="delta", session=session)
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN, tenant="delta")
    first = await async_client.get("/api/v1/contractors/registry", headers=headers)
    assert first.status_code == status.HTTP_200_OK
    assert first.json()["items"] == []
    etag = first.headers["ETag"]
    assert etag

    second = await async_client.get(
        "/api/v1/contractors/registry", headers={**headers, "If-None-Match": etag}
    )
    assert second.status_code == status.HTTP_304_NOT_MODIFIED


# =============================================================================
# /api/v1/journals
# =============================================================================


@pytest.mark.asyncio
async def test_journals_hit_returns_304(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        await session.commit()
        company_id = str(company.id)

    headers = await make_auth_headers(RoleEnum.ADMIN)
    await _seed_journal(async_client, headers, company_id=company_id, title="Hit Journal")

    first = await async_client.get("/api/v1/journals", headers=headers)
    assert first.status_code == status.HTTP_200_OK
    etag = first.headers["ETag"]

    second = await async_client.get(
        "/api/v1/journals", headers={**headers, "If-None-Match": etag}
    )
    assert second.status_code == status.HTTP_304_NOT_MODIFIED
    assert second.headers["ETag"] == etag
    assert second.content == b""


@pytest.mark.asyncio
async def test_journals_miss_with_bogus_etag(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        await session.commit()
        company_id = str(company.id)

    headers = await make_auth_headers(RoleEnum.ADMIN)
    await _seed_journal(async_client, headers, company_id=company_id, title="Miss Journal")

    response = await async_client.get(
        "/api/v1/journals", headers={**headers, "If-None-Match": '"stale-journal"'}
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["items"]


@pytest.mark.asyncio
async def test_journals_etag_changes_after_create(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        await session.commit()
        company_id = str(company.id)

    headers = await make_auth_headers(RoleEnum.ADMIN)
    await _seed_journal(async_client, headers, company_id=company_id, title="Before-POST")
    first = await async_client.get("/api/v1/journals", headers=headers)
    initial_etag = first.headers["ETag"]

    await _seed_journal(async_client, headers, company_id=company_id, title="After-POST")

    second = await async_client.get("/api/v1/journals", headers=headers)
    assert second.headers["ETag"] != initial_etag


@pytest.mark.asyncio
async def test_journals_etag_distinct_per_company_filter(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company_a = await data_factory.create_company(tenant=tenant, name="A Co", session=session)
        company_b = await data_factory.create_company(tenant=tenant, name="B Co", session=session)
        await session.commit()
        company_a_id, company_b_id = str(company_a.id), str(company_b.id)

    headers = await make_auth_headers(RoleEnum.ADMIN)
    await _seed_journal(async_client, headers, company_id=company_a_id, title="J A")
    await _seed_journal(async_client, headers, company_id=company_b_id, title="J B")

    unfiltered = await async_client.get("/api/v1/journals", headers=headers)
    filtered_a = await async_client.get(
        f"/api/v1/journals?company_id={company_a_id}", headers=headers
    )
    assert unfiltered.headers["ETag"] != filtered_a.headers["ETag"]


@pytest.mark.asyncio
async def test_journals_empty_list_stable_etag(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(slug="gamma", session=session)
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN, tenant="gamma")
    first = await async_client.get("/api/v1/journals", headers=headers)
    assert first.status_code == status.HTTP_200_OK
    assert first.json()["items"] == []
    etag = first.headers["ETag"]
    assert etag

    second = await async_client.get(
        "/api/v1/journals", headers={**headers, "If-None-Match": etag}
    )
    assert second.status_code == status.HTTP_304_NOT_MODIFIED
