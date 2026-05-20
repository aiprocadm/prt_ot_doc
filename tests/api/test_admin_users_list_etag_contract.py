"""HTTP cache (ETag / If-None-Match) contract + base CRUD pin for
/api/v1/admin/users (Phase 9.2 extension / vNext-PERF-03, Session 57).

S57 introduces a new admin list endpoint that didn't exist before — previously
``admin_users.py`` only exposed per-user role/attribute routes. The new
``GET /admin/users`` powers the "Manage Users" admin page referenced from
``workspace.py:662`` and ships with ETag conditional-GET from day one.

The auth user itself is a row in ``user`` table — every authenticated request
to this endpoint sees at least one row (the caller). "Empty-list" tests
therefore use a role filter that matches no rows.

After S57, coverage extends to 24 list endpoints carrying ETag conditional-GET.

Pinned axes: hit/miss/filter (role/active/company)/page/cross-tenant anti-leak/
invalid-role 422/empty-by-filter-stable.
"""

from __future__ import annotations

import pytest
from fastapi import status
from httpx import AsyncClient

from app.models.models import RoleEnum
from tests.utils.factories import TestDataFactory


# =============================================================================
# /api/v1/admin/users — base list contract
# =============================================================================


@pytest.mark.asyncio
async def test_admin_users_list_returns_caller(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    """Sanity: a freshly-authenticated admin sees themselves in the list."""
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN)
    response = await async_client.get("/api/v1/admin/users", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["total"] >= 1
    assert any(item["role"] == "admin" for item in body["items"])


@pytest.mark.asyncio
async def test_admin_users_list_omits_hashed_password(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    """Security: hashed_password must NEVER appear in the API response."""
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN)
    response = await async_client.get("/api/v1/admin/users", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    for item in response.json()["items"]:
        assert "hashed_password" not in item
        assert "password" not in item


@pytest.mark.asyncio
async def test_admin_users_list_rejects_non_admin(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    """RBAC: only admin/owner can list users; HR should be forbidden."""
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()

    headers = await make_auth_headers(RoleEnum.HR)
    response = await async_client.get("/api/v1/admin/users", headers=headers)
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_admin_users_list_invalid_role_422(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    """Bad ?role= → 422 with admin error code."""
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN)
    response = await async_client.get(
        "/api/v1/admin/users?role=nosuchrole", headers=headers
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


# =============================================================================
# /api/v1/admin/users — ETag conditional-GET
# =============================================================================


@pytest.mark.asyncio
async def test_admin_users_hit_returns_304(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN)
    first = await async_client.get("/api/v1/admin/users", headers=headers)
    assert first.status_code == status.HTTP_200_OK
    etag = first.headers["ETag"]

    second = await async_client.get(
        "/api/v1/admin/users", headers={**headers, "If-None-Match": etag}
    )
    assert second.status_code == status.HTTP_304_NOT_MODIFIED
    assert second.headers["ETag"] == etag
    assert second.content == b""


@pytest.mark.asyncio
async def test_admin_users_miss_with_bogus_etag(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN)
    response = await async_client.get(
        "/api/v1/admin/users", headers={**headers, "If-None-Match": '"stale-user"'}
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["items"]


@pytest.mark.asyncio
async def test_admin_users_etag_changes_after_user_added(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN)
    first = await async_client.get("/api/v1/admin/users", headers=headers)
    initial_etag = first.headers["ETag"]

    async with sessionmaker() as session:
        await data_factory.create_user(
            tenant=tenant,
            email="newhire@example.com",
            role=RoleEnum.WORKER,
            session=session,
        )
        await session.commit()

    second = await async_client.get("/api/v1/admin/users", headers=headers)
    assert second.headers["ETag"] != initial_etag


@pytest.mark.asyncio
async def test_admin_users_etag_distinct_per_role_filter(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        await data_factory.create_user(
            tenant=tenant, email="hr1@example.com", role=RoleEnum.HR, session=session
        )
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN)
    unfiltered = await async_client.get("/api/v1/admin/users", headers=headers)
    filtered = await async_client.get(
        "/api/v1/admin/users?role=hr", headers=headers
    )
    assert unfiltered.headers["ETag"] != filtered.headers["ETag"]


@pytest.mark.asyncio
async def test_admin_users_etag_distinct_per_active_filter(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    """is_active=true / =false / unset → 3 distinct ETags (boolean 3-state)."""
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        await data_factory.create_user(
            tenant=tenant,
            email="inactive@example.com",
            role=RoleEnum.WORKER,
            is_active=False,
            session=session,
        )
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN)
    no_filter = await async_client.get("/api/v1/admin/users", headers=headers)
    active_true = await async_client.get(
        "/api/v1/admin/users?is_active=true", headers=headers
    )
    active_false = await async_client.get(
        "/api/v1/admin/users?is_active=false", headers=headers
    )
    etags = {
        no_filter.headers["ETag"],
        active_true.headers["ETag"],
        active_false.headers["ETag"],
    }
    assert len(etags) == 3


@pytest.mark.asyncio
async def test_admin_users_etag_distinct_per_company_filter(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company_a = await data_factory.create_company(tenant=tenant, name="A Co", session=session)
        await data_factory.create_user(
            tenant=tenant,
            email="emp-a@example.com",
            role=RoleEnum.WORKER,
            company_id=company_a.id,
            session=session,
        )
        await session.commit()
        company_a_id = str(company_a.id)

    headers = await make_auth_headers(RoleEnum.ADMIN)
    unfiltered = await async_client.get("/api/v1/admin/users", headers=headers)
    filtered = await async_client.get(
        f"/api/v1/admin/users?company_id={company_a_id}", headers=headers
    )
    assert unfiltered.headers["ETag"] != filtered.headers["ETag"]


@pytest.mark.asyncio
async def test_admin_users_etag_distinct_per_page(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        for i in range(4):
            await data_factory.create_user(
                tenant=tenant,
                email=f"page{i}@example.com",
                role=RoleEnum.WORKER,
                session=session,
            )
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN)
    page_a = await async_client.get(
        "/api/v1/admin/users?limit=2&offset=0", headers=headers
    )
    page_b = await async_client.get(
        "/api/v1/admin/users?limit=2&offset=2", headers=headers
    )
    assert page_a.headers["ETag"] != page_b.headers["ETag"]


@pytest.mark.asyncio
async def test_admin_users_empty_by_filter_stable_etag(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    """When filter matches no rows → empty list + stable ETag → 304 on revisit.

    Cannot test truly empty tenant — calling admin is itself a row. Use
    ?role=teacher on tenant where only admin exists.
    """
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(slug="users-tch", session=session)
        await session.commit()

    headers = await make_auth_headers(
        RoleEnum.ADMIN, tenant="users-tch", email="admin-tch@example.com"
    )
    first = await async_client.get(
        "/api/v1/admin/users?role=teacher", headers=headers
    )
    assert first.status_code == status.HTTP_200_OK
    assert first.json()["items"] == []
    etag = first.headers["ETag"]
    assert etag

    second = await async_client.get(
        "/api/v1/admin/users?role=teacher",
        headers={**headers, "If-None-Match": etag},
    )
    assert second.status_code == status.HTTP_304_NOT_MODIFIED


@pytest.mark.asyncio
async def test_admin_users_cross_tenant_etag_does_not_leak(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    """User list is org-sensitive — cross-tenant 304 leak would expose org structure."""
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(slug="users-acme", session=session)
        await data_factory.ensure_tenant(slug="users-beta", session=session)
        await session.commit()

    headers_a = await make_auth_headers(
        RoleEnum.ADMIN, tenant="users-acme", email="admin-users-acme@example.com"
    )
    headers_b = await make_auth_headers(
        RoleEnum.ADMIN, tenant="users-beta", email="admin-users-beta@example.com"
    )

    a = await async_client.get("/api/v1/admin/users", headers=headers_a)
    etag_a = a.headers["ETag"]

    leaked = await async_client.get(
        "/api/v1/admin/users", headers={**headers_b, "If-None-Match": etag_a}
    )
    assert leaked.status_code == status.HTTP_200_OK
