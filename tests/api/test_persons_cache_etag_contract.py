"""HTTP cache (ETag / If-None-Match) contract for /api/v1/persons
(Phase 9.2 extension / vNext-PERF-03, Session 48).

Mirrors the contract pinned by :mod:`tests.api.test_http_cache_etag_contract`
for the other four list endpoints (companies / sites / documents / tasks),
applied to the newly-added persons list ETag. The endpoint is high-traffic
(employee directory page) and benefits the most from conditional GET on
subsequent navigation.

Covers: hit (304 + same ETag + empty body); miss (bogus ETag → 200 + body);
mutation invalidation (POST changes ETag on next list); pagination isolation
(`limit`/`offset` parameters are part of the cache key); tenant isolation
(cross-tenant ETag leak rejected); empty-list stable ETag; RFC 7232 quoted
string; deterministic across repeats.
"""

from __future__ import annotations

import pytest
from fastapi import status
from httpx import AsyncClient

from app.models.models import RoleEnum
from tests.utils.factories import TestDataFactory


@pytest.mark.asyncio
async def test_persons_hit_returns_304_with_same_etag(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    """Identical request after first read → 304 + same ETag + empty body."""
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        await data_factory.create_person(
            tenant=tenant, first_name="Ada", last_name="Lovelace", session=session
        )
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN)
    first = await async_client.get("/api/v1/persons", headers=headers)
    assert first.status_code == status.HTTP_200_OK
    etag = first.headers["ETag"]

    second = await async_client.get(
        "/api/v1/persons", headers={**headers, "If-None-Match": etag}
    )
    assert second.status_code == status.HTTP_304_NOT_MODIFIED
    assert second.headers["ETag"] == etag
    assert second.content == b""


@pytest.mark.asyncio
async def test_persons_miss_with_bogus_etag_returns_200_and_body(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    """Wrong ETag → 200 with full body, fresh ETag in response."""
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        await data_factory.create_person(
            tenant=tenant, first_name="Grace", last_name="Hopper", session=session
        )
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN)
    response = await async_client.get(
        "/api/v1/persons", headers={**headers, "If-None-Match": '"stale-etag-beef"'}
    )
    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["items"], "Body should be present when ETag mismatches"
    assert response.headers["ETag"] != '"stale-etag-beef"'


@pytest.mark.asyncio
async def test_persons_etag_changes_after_create(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    """Write-through invalidation: POST changes ETag on subsequent list.

    A client holding a stale ETag must see 200 (not 304) after creating a
    new person — so it observes its own write.
    """
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(
            tenant=tenant, name="Persons Holdco", session=session
        )
        await data_factory.create_person(
            tenant=tenant, company=company, first_name="Before", last_name="POST", session=session
        )
        await session.commit()
        company_id = str(company.id)

    headers = await make_auth_headers(RoleEnum.ADMIN)
    first = await async_client.get("/api/v1/persons", headers=headers)
    initial_etag = first.headers["ETag"]

    create = await async_client.post(
        "/api/v1/persons",
        json={
            "company_id": company_id,
            "first_name": "After",
            "last_name": "Post",
        },
        headers=headers,
    )
    assert create.status_code == status.HTTP_201_CREATED

    second = await async_client.get(
        "/api/v1/persons", headers={**headers, "If-None-Match": initial_etag}
    )
    assert second.status_code == status.HTTP_200_OK
    assert second.headers["ETag"] != initial_etag


@pytest.mark.asyncio
async def test_persons_etag_changes_after_patch(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    """PATCH on a member row must invalidate the list ETag (updated_at changes)."""
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        person = await data_factory.create_person(
            tenant=tenant, first_name="PatchTarget", last_name="Original", session=session
        )
        await session.commit()
        person_id = str(person.id)

    headers = await make_auth_headers(RoleEnum.ADMIN)
    first = await async_client.get("/api/v1/persons", headers=headers)
    initial_etag = first.headers["ETag"]

    patch = await async_client.patch(
        f"/api/v1/persons/{person_id}",
        json={"first_name": "PatchedFirstName"},
        headers=headers,
    )
    assert patch.status_code == status.HTTP_200_OK

    second = await async_client.get("/api/v1/persons", headers=headers)
    assert second.headers["ETag"] != initial_etag


@pytest.mark.asyncio
async def test_persons_etag_distinct_per_page(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    """Different ``offset`` → different ETag (no page collision)."""
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(
            tenant=tenant, name="MultiPagePersons", session=session
        )
        for i in range(5):
            await data_factory.create_person(
                tenant=tenant, company=company,
                first_name=f"Page{i}", last_name=f"User{i}",
                session=session,
            )
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN)
    page_a = await async_client.get("/api/v1/persons?limit=2&offset=0", headers=headers)
    page_b = await async_client.get("/api/v1/persons?limit=2&offset=2", headers=headers)
    assert page_a.status_code == status.HTTP_200_OK
    assert page_b.status_code == status.HTTP_200_OK
    assert page_a.headers["ETag"] != page_b.headers["ETag"]


@pytest.mark.asyncio
async def test_persons_etag_distinct_per_limit(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    """``limit`` is part of cache key — same data but different limit ≠ same ETag."""
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(
            tenant=tenant, name="LimitPersons", session=session
        )
        for i in range(3):
            await data_factory.create_person(
                tenant=tenant, company=company,
                first_name=f"Lim{i}", last_name=f"Test{i}",
                session=session,
            )
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN)
    a = await async_client.get("/api/v1/persons?limit=1", headers=headers)
    b = await async_client.get("/api/v1/persons?limit=50", headers=headers)
    assert a.headers["ETag"] != b.headers["ETag"]


@pytest.mark.asyncio
async def test_persons_empty_list_has_stable_etag(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    """Empty result still produces a stable, valid ETag (conditional GET works on zero rows)."""
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(slug="epsilon", session=session)
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN, tenant="epsilon")
    first = await async_client.get("/api/v1/persons", headers=headers)
    assert first.status_code == status.HTTP_200_OK
    assert first.json()["items"] == []
    etag_first = first.headers["ETag"]
    assert etag_first

    second = await async_client.get(
        "/api/v1/persons", headers={**headers, "If-None-Match": etag_first}
    )
    assert second.status_code == status.HTTP_304_NOT_MODIFIED
    assert second.headers["ETag"] == etag_first


@pytest.mark.asyncio
async def test_persons_etag_isolated_across_tenants(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    """Identical person names across tenants → distinct ETags.

    Tenant prefix (`tenant:{tenant_id}`) is baked into the hash; a regression
    that drops it would let one tenant cache another's data.
    """
    async with sessionmaker() as session:
        tenant_a = await data_factory.ensure_tenant(slug="acme", session=session)
        tenant_b = await data_factory.ensure_tenant(slug="beta", session=session)
        await data_factory.create_person(
            tenant=tenant_a, first_name="Same", last_name="Name", session=session
        )
        await data_factory.create_person(
            tenant=tenant_b, first_name="Same", last_name="Name", session=session
        )
        await session.commit()

    headers_a = await make_auth_headers(RoleEnum.ADMIN, tenant="acme")
    headers_b = await make_auth_headers(RoleEnum.ADMIN, tenant="beta")
    a = await async_client.get("/api/v1/persons", headers=headers_a)
    b = await async_client.get("/api/v1/persons", headers=headers_b)
    assert a.headers["ETag"] != b.headers["ETag"]


@pytest.mark.asyncio
async def test_persons_cross_tenant_etag_does_not_match(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    """Tenant A's ETag presented in tenant B's request must return 200, not 304.

    Anti-leak: a regression dropping tenant-scoping from the ETag would let
    a malicious client guess another tenant's hash and observe their list state.
    """
    async with sessionmaker() as session:
        tenant_a = await data_factory.ensure_tenant(slug="acme", session=session)
        tenant_b = await data_factory.ensure_tenant(slug="beta", session=session)
        await data_factory.create_person(
            tenant=tenant_a, first_name="A", last_name="Person", session=session
        )
        await data_factory.create_person(
            tenant=tenant_b, first_name="B", last_name="Person", session=session
        )
        await session.commit()

    headers_a = await make_auth_headers(RoleEnum.ADMIN, tenant="acme")
    headers_b = await make_auth_headers(RoleEnum.ADMIN, tenant="beta")
    a = await async_client.get("/api/v1/persons", headers=headers_a)
    etag_a = a.headers["ETag"]

    leaked = await async_client.get(
        "/api/v1/persons", headers={**headers_b, "If-None-Match": etag_a}
    )
    assert leaked.status_code == status.HTTP_200_OK


@pytest.mark.asyncio
async def test_persons_etag_is_quoted_per_rfc7232(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    """RFC 7232: ETag must be a quoted-string (``"..."``)."""
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        await data_factory.create_person(
            tenant=tenant, first_name="Quoted", last_name="Format", session=session
        )
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN)
    response = await async_client.get("/api/v1/persons", headers=headers)
    etag = response.headers["ETag"]
    assert etag.startswith('"') and etag.endswith('"'), f"ETag not quoted: {etag!r}"


@pytest.mark.asyncio
async def test_persons_etag_deterministic_across_repeated_reads(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    """Same data + same request 3 times → identical ETag (deterministic hash)."""
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        await data_factory.create_person(
            tenant=tenant, first_name="Stable", last_name="Hash", session=session
        )
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN)
    etags = []
    for _ in range(3):
        response = await async_client.get("/api/v1/persons", headers=headers)
        etags.append(response.headers["ETag"])
    assert etags[0] == etags[1] == etags[2]
