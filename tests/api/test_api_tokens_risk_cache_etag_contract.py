"""HTTP cache (ETag / If-None-Match) contract for /api/v1/api-tokens +
/api/v1/risk/methodologies + /api/v1/risk/maps (Phase 9.2 extension /
vNext-PERF-03, Session 55).

Continues the rollout. Three endpoints:

- ``/api-tokens`` — flat list (no pagination), highly sensitive (security
  credentials) → cross-tenant anti-leak test is mandatory.
- ``/risk/methodologies`` — flat list. Public API POST yields mutation
  invalidation contract.
- ``/risk/maps`` — flat list with mandatory ``company_id`` filter + optional
  site/position/methodology filters. Risk map seeding goes through ORM
  (POST chain requires methodology + matrix recalculation).

After S55, coverage extends to 21 list endpoints carrying ETag conditional-GET.

Pinned axes: hit/miss/mutation invalidation/cross-tenant anti-leak/empty-stable/
filter isolation.
"""

from __future__ import annotations

import pytest
from fastapi import status
from httpx import AsyncClient

from app.models.models import RiskMap, RiskMethodology, RoleEnum
from tests.utils.factories import TestDataFactory


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------


async def _seed_api_token(
    async_client: AsyncClient,
    headers: dict,
    *,
    name: str = "ci-token",
) -> dict:
    payload: dict = {"name": name, "scopes": ["read"]}
    response = await async_client.post(
        "/api/v1/api-tokens", json=payload, headers=headers
    )
    assert response.status_code == status.HTTP_201_CREATED, response.text
    return response.json()


async def _seed_methodology_via_api(
    async_client: AsyncClient,
    headers: dict,
    *,
    name: str = "Test Matrix",
) -> dict:
    payload: dict = {
        "name": name,
        "bands": [
            {"name": "low", "max": 4},
            {"name": "med", "max": 8},
            {"name": "high", "max": 25},
        ],
    }
    response = await async_client.post(
        "/api/v1/risk/methodologies", json=payload, headers=headers
    )
    assert response.status_code == status.HTTP_200_OK, response.text
    return response.json()


async def _seed_risk_map(
    session,
    *,
    tenant_id: str,
    methodology_id: str,
    company_id: str,
    site_id: str | None = None,
    position_id: str | None = None,
) -> RiskMap:
    """Seed a RiskMap directly via ORM (POST chain requires matrix recalculation)."""
    risk_map = RiskMap(
        tenant_id=tenant_id,
        methodology_id=methodology_id,
        company_id=company_id,
        site_id=site_id,
        position_id=position_id,
        matrix={"cells": []},
    )
    session.add(risk_map)
    await session.flush()
    return risk_map


async def _seed_methodology_orm(
    session, *, tenant_id: str, name: str = "ORM Matrix", code: str = "orm-mx"
) -> RiskMethodology:
    methodology = RiskMethodology(
        tenant_id=tenant_id,
        name=name,
        code=code,
        definition={"severity_scale": [], "likelihood_scale": [], "bands": []},
        version=1,
    )
    session.add(methodology)
    await session.flush()
    return methodology


# =============================================================================
# /api/v1/api-tokens
# =============================================================================


@pytest.mark.asyncio
async def test_api_tokens_hit_returns_304(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()

    headers = await make_auth_headers(RoleEnum.OWNER)
    await _seed_api_token(async_client, headers, name="hit-token")

    first = await async_client.get("/api/v1/api-tokens", headers=headers)
    assert first.status_code == status.HTTP_200_OK
    etag = first.headers["ETag"]

    second = await async_client.get(
        "/api/v1/api-tokens", headers={**headers, "If-None-Match": etag}
    )
    assert second.status_code == status.HTTP_304_NOT_MODIFIED
    assert second.headers["ETag"] == etag
    assert second.content == b""


@pytest.mark.asyncio
async def test_api_tokens_miss_with_bogus_etag(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()

    headers = await make_auth_headers(RoleEnum.OWNER)
    await _seed_api_token(async_client, headers, name="miss-token")

    response = await async_client.get(
        "/api/v1/api-tokens", headers={**headers, "If-None-Match": '"stale-token"'}
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()


@pytest.mark.asyncio
async def test_api_tokens_etag_changes_after_create(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()

    headers = await make_auth_headers(RoleEnum.OWNER)
    await _seed_api_token(async_client, headers, name="before-token")
    first = await async_client.get("/api/v1/api-tokens", headers=headers)
    initial_etag = first.headers["ETag"]

    await _seed_api_token(async_client, headers, name="after-token")

    second = await async_client.get("/api/v1/api-tokens", headers=headers)
    assert second.headers["ETag"] != initial_etag


@pytest.mark.asyncio
async def test_api_tokens_empty_list_stable_etag(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(slug="empty-tk", session=session)
        await session.commit()

    headers = await make_auth_headers(RoleEnum.OWNER, tenant="empty-tk")
    first = await async_client.get("/api/v1/api-tokens", headers=headers)
    assert first.status_code == status.HTTP_200_OK
    assert first.json() == []
    etag = first.headers["ETag"]
    assert etag

    second = await async_client.get(
        "/api/v1/api-tokens", headers={**headers, "If-None-Match": etag}
    )
    assert second.status_code == status.HTTP_304_NOT_MODIFIED


@pytest.mark.asyncio
async def test_api_tokens_cross_tenant_etag_does_not_leak(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    """API tokens are security credentials — cross-tenant leak would be a breach."""
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(slug="tk-acme", session=session)
        await data_factory.ensure_tenant(slug="tk-beta", session=session)
        await session.commit()

    headers_a = await make_auth_headers(
        RoleEnum.OWNER, tenant="tk-acme", email="owner-tk-acme@example.com"
    )
    headers_b = await make_auth_headers(
        RoleEnum.OWNER, tenant="tk-beta", email="owner-tk-beta@example.com"
    )
    await _seed_api_token(async_client, headers_a, name="Same Name")
    await _seed_api_token(async_client, headers_b, name="Same Name")

    a = await async_client.get("/api/v1/api-tokens", headers=headers_a)
    etag_a = a.headers["ETag"]

    leaked = await async_client.get(
        "/api/v1/api-tokens", headers={**headers_b, "If-None-Match": etag_a}
    )
    assert leaked.status_code == status.HTTP_200_OK


# =============================================================================
# /api/v1/risk/methodologies
# =============================================================================


@pytest.mark.asyncio
async def test_risk_methodologies_hit_returns_304(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN)
    await _seed_methodology_via_api(async_client, headers, name="Hit Matrix")

    first = await async_client.get("/api/v1/risk/methodologies", headers=headers)
    assert first.status_code == status.HTTP_200_OK
    etag = first.headers["ETag"]

    second = await async_client.get(
        "/api/v1/risk/methodologies", headers={**headers, "If-None-Match": etag}
    )
    assert second.status_code == status.HTTP_304_NOT_MODIFIED
    assert second.content == b""


@pytest.mark.asyncio
async def test_risk_methodologies_miss_with_bogus_etag(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN)
    await _seed_methodology_via_api(async_client, headers, name="Miss Matrix")

    response = await async_client.get(
        "/api/v1/risk/methodologies",
        headers={**headers, "If-None-Match": '"stale-methodology"'},
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()


@pytest.mark.asyncio
async def test_risk_methodologies_etag_changes_after_create(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN)
    await _seed_methodology_via_api(async_client, headers, name="Before Matrix")
    first = await async_client.get("/api/v1/risk/methodologies", headers=headers)
    initial_etag = first.headers["ETag"]

    await _seed_methodology_via_api(async_client, headers, name="After Matrix")

    second = await async_client.get("/api/v1/risk/methodologies", headers=headers)
    assert second.headers["ETag"] != initial_etag


@pytest.mark.asyncio
async def test_risk_methodologies_empty_list_stable_etag(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(slug="risk-empty", session=session)
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN, tenant="risk-empty")
    first = await async_client.get("/api/v1/risk/methodologies", headers=headers)
    assert first.status_code == status.HTTP_200_OK
    assert first.json() == []
    etag = first.headers["ETag"]
    assert etag

    second = await async_client.get(
        "/api/v1/risk/methodologies", headers={**headers, "If-None-Match": etag}
    )
    assert second.status_code == status.HTTP_304_NOT_MODIFIED


# =============================================================================
# /api/v1/risk/maps
# =============================================================================


@pytest.mark.asyncio
async def test_risk_maps_hit_returns_304(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        methodology = await _seed_methodology_orm(
            session, tenant_id=str(tenant.id), name="Hit Maps Matrix"
        )
        await _seed_risk_map(
            session,
            tenant_id=str(tenant.id),
            methodology_id=str(methodology.id),
            company_id=str(company.id),
        )
        await session.commit()
        company_id = str(company.id)

    headers = await make_auth_headers(RoleEnum.ADMIN)
    first = await async_client.get(
        f"/api/v1/risk/maps?company_id={company_id}", headers=headers
    )
    assert first.status_code == status.HTTP_200_OK
    etag = first.headers["ETag"]

    second = await async_client.get(
        f"/api/v1/risk/maps?company_id={company_id}",
        headers={**headers, "If-None-Match": etag},
    )
    assert second.status_code == status.HTTP_304_NOT_MODIFIED
    assert second.content == b""


@pytest.mark.asyncio
async def test_risk_maps_etag_distinct_per_methodology_filter(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        methodology_a = await _seed_methodology_orm(
            session, tenant_id=str(tenant.id), name="A Matrix", code="a-mx"
        )
        methodology_b = await _seed_methodology_orm(
            session, tenant_id=str(tenant.id), name="B Matrix", code="b-mx"
        )
        await _seed_risk_map(
            session,
            tenant_id=str(tenant.id),
            methodology_id=str(methodology_a.id),
            company_id=str(company.id),
        )
        await _seed_risk_map(
            session,
            tenant_id=str(tenant.id),
            methodology_id=str(methodology_b.id),
            company_id=str(company.id),
        )
        await session.commit()
        company_id = str(company.id)
        methodology_a_id = str(methodology_a.id)

    headers = await make_auth_headers(RoleEnum.ADMIN)
    unfiltered = await async_client.get(
        f"/api/v1/risk/maps?company_id={company_id}", headers=headers
    )
    filtered = await async_client.get(
        f"/api/v1/risk/maps?company_id={company_id}&methodology_id={methodology_a_id}",
        headers=headers,
    )
    assert unfiltered.headers["ETag"] != filtered.headers["ETag"]


@pytest.mark.asyncio
async def test_risk_maps_empty_list_stable_etag(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        await session.commit()
        company_id = str(company.id)

    headers = await make_auth_headers(RoleEnum.ADMIN)
    first = await async_client.get(
        f"/api/v1/risk/maps?company_id={company_id}", headers=headers
    )
    assert first.status_code == status.HTTP_200_OK
    assert first.json() == []
    etag = first.headers["ETag"]
    assert etag

    second = await async_client.get(
        f"/api/v1/risk/maps?company_id={company_id}",
        headers={**headers, "If-None-Match": etag},
    )
    assert second.status_code == status.HTTP_304_NOT_MODIFIED
