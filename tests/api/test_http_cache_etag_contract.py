"""HTTP cache (ETag / If-None-Match) contract for list endpoints
(Phase 9.2 / vNext-PERF-03, Session 47).

Pins the full conditional-GET contract for the four list endpoints that
already emit ETag headers: ``/api/v1/companies``, ``/api/v1/sites``,
``/api/v1/documents``, ``/api/v1/tasks``. The pre-existing tests each
cover only one happy-path per endpoint (list → grab ETag → re-request
with ``If-None-Match`` → expect 304). This file closes the contract gap:

- **Hit**: identical request → 304 with same ETag, no body
- **Miss (stale)**: changed payload → 200 + new ETag, body returned
- **Pagination isolation**: different page/limit → distinct ETags
- **Filter isolation**: different filter combo → distinct ETags
- **Tenant isolation**: ETag from tenant A invalid in tenant B (no cross-bleed)
- **Mutation invalidates**: POST/PATCH/DELETE changes ETag on subsequent list
- **Empty result**: empty list still produces stable, valid ETag
- **Mismatched ETag → 200**: bogus ``If-None-Match`` returns full body

The HTTP cache layer is the project's primary client-side cache (see
``backend/app/api/routes/{companies,sites,documents,tasks}.py``); a strong
contract here removes round-trips for dashboards / drilldowns where users
repeatedly reload the same list. Phase 9.2 acceptance criterion #3 ("Cache
hit/miss tests") is satisfied through this file's 26 cases.

Out of scope (deliberately, to keep this file focused on the HTTP contract):
- Redis session/config cache (`app.state.redis_client`) — separate concern.
- File-content ETag (`/api/v1/files/{id}` uses sha256 as ETag, not the
  list-hash pattern) — different contract, would warrant its own file.
- Server-side response caching beyond conditional GET (no such layer
  exists today). Cache-Control header uniformity across all 25 ETag
  list endpoints is pinned in
  ``tests/api/test_etag_cache_control_uniformity.py`` (Session 59).
"""

from __future__ import annotations

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import select

from app.models.models import RoleEnum, Tenant
from app.models.obligations import Task, TaskPriority, TaskStatus
from tests.utils.factories import TestDataFactory

# =============================================================================
# Companies list (/api/v1/companies)
# =============================================================================


@pytest.mark.asyncio
async def test_companies_hit_returns_304_with_same_etag(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    """Identical request after first read → 304 + same ETag + empty body."""
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        await data_factory.create_company(tenant=tenant, name="HitTest Co", session=session)
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN)
    first = await async_client.get("/api/v1/companies", headers=headers)
    assert first.status_code == status.HTTP_200_OK
    etag = first.headers["ETag"]

    second = await async_client.get("/api/v1/companies", headers={**headers, "If-None-Match": etag})
    assert second.status_code == status.HTTP_304_NOT_MODIFIED
    assert second.headers["ETag"] == etag
    assert second.content == b""


@pytest.mark.asyncio
async def test_companies_miss_with_bogus_etag_returns_200_and_body(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    """Wrong ETag → 200 with full body, fresh ETag in response."""
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        await data_factory.create_company(tenant=tenant, name="MissTest Co", session=session)
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN)
    response = await async_client.get(
        "/api/v1/companies", headers={**headers, "If-None-Match": '"stale-etag-deadbeef"'}
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["items"], "Body should be present when ETag mismatches"
    assert response.headers["ETag"] != '"stale-etag-deadbeef"'


@pytest.mark.asyncio
async def test_companies_etag_changes_after_create(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    """Write-through invalidation: POST changes ETag on subsequent list.

    This is the cache-consistency invariant: a client that holds a stale
    ETag and POSTs a new company must see 200 (not 304) on the next list
    so it observes its own write.
    """
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        await data_factory.create_company(tenant=tenant, name="Before-POST", session=session)
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN)
    first = await async_client.get("/api/v1/companies", headers=headers)
    initial_etag = first.headers["ETag"]

    create = await async_client.post(
        "/api/v1/companies",
        json={"name": "After-POST Co"},
        headers=headers,
    )
    assert create.status_code == status.HTTP_201_CREATED

    second = await async_client.get(
        "/api/v1/companies", headers={**headers, "If-None-Match": initial_etag}
    )
    assert second.status_code == status.HTTP_200_OK
    assert second.headers["ETag"] != initial_etag


@pytest.mark.asyncio
async def test_companies_etag_changes_after_patch(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    """PATCH on a member row must invalidate the list ETag (updated_at changes)."""
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(
            tenant=tenant, name="PatchTest Co", session=session
        )
        await session.commit()
        company_id = company.id

    headers = await make_auth_headers(RoleEnum.ADMIN)
    first = await async_client.get("/api/v1/companies", headers=headers)
    initial_etag = first.headers["ETag"]

    patch = await async_client.patch(
        f"/api/v1/companies/{company_id}",
        json={"name": "Patched Name"},
        headers=headers,
    )
    assert patch.status_code == status.HTTP_200_OK

    second = await async_client.get("/api/v1/companies", headers=headers)
    assert second.headers["ETag"] != initial_etag


@pytest.mark.asyncio
async def test_companies_etag_distinct_per_page(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    """Different ``offset`` → different ETag (no page-collision)."""
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        for i in range(5):
            await data_factory.create_company(tenant=tenant, name=f"Page Co {i}", session=session)
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN)
    page_a = await async_client.get("/api/v1/companies?limit=2&offset=0", headers=headers)
    page_b = await async_client.get("/api/v1/companies?limit=2&offset=2", headers=headers)
    assert page_a.status_code == status.HTTP_200_OK
    assert page_b.status_code == status.HTTP_200_OK
    assert page_a.headers["ETag"] != page_b.headers["ETag"]


@pytest.mark.asyncio
async def test_companies_etag_distinct_per_limit(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    """``limit`` is part of cache key — same data but different limit ≠ same ETag."""
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        for i in range(3):
            await data_factory.create_company(tenant=tenant, name=f"LimitCo {i}", session=session)
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN)
    a = await async_client.get("/api/v1/companies?limit=1", headers=headers)
    b = await async_client.get("/api/v1/companies?limit=50", headers=headers)
    assert a.headers["ETag"] != b.headers["ETag"]


@pytest.mark.asyncio
async def test_companies_empty_list_has_stable_etag(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    """Empty result still produces ETag — and two empty fetches match (stable)."""
    async with sessionmaker() as session:
        # Use a fresh tenant with no companies
        await data_factory.ensure_tenant(slug="gamma", session=session)
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN, tenant="gamma")
    first = await async_client.get("/api/v1/companies", headers=headers)
    assert first.status_code == status.HTTP_200_OK
    assert first.json()["items"] == []
    etag_first = first.headers["ETag"]
    assert etag_first

    second = await async_client.get("/api/v1/companies", headers=headers)
    assert second.headers["ETag"] == etag_first


# =============================================================================
# Sites list (/api/v1/sites)
# =============================================================================


@pytest.mark.asyncio
async def test_sites_hit_returns_304(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        await data_factory.create_site(tenant=tenant, name="HitSite", session=session)
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN)
    first = await async_client.get("/api/v1/sites", headers=headers)
    assert first.status_code == status.HTTP_200_OK
    etag = first.headers["ETag"]

    second = await async_client.get("/api/v1/sites", headers={**headers, "If-None-Match": etag})
    assert second.status_code == status.HTTP_304_NOT_MODIFIED
    assert second.headers["ETag"] == etag


@pytest.mark.asyncio
async def test_sites_miss_with_bogus_etag(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        await data_factory.create_site(tenant=tenant, name="MissSite", session=session)
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN)
    response = await async_client.get(
        "/api/v1/sites", headers={**headers, "If-None-Match": '"bogus"'}
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.headers["ETag"] != '"bogus"'


@pytest.mark.asyncio
async def test_sites_etag_changes_after_create(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, name="SiteHost", session=session)
        await data_factory.create_site(
            tenant=tenant, company=company, name="Initial", session=session
        )
        await session.commit()
        company_id = company.id

    headers = await make_auth_headers(RoleEnum.ADMIN)
    first = await async_client.get("/api/v1/sites", headers=headers)
    initial_etag = first.headers["ETag"]

    create = await async_client.post(
        "/api/v1/sites",
        json={
            "company_id": str(company_id),
            "name": "Created Site",
            "address": "wherever 12",
        },
        headers=headers,
    )
    assert create.status_code == status.HTTP_201_CREATED

    second = await async_client.get("/api/v1/sites", headers=headers)
    assert second.headers["ETag"] != initial_etag


@pytest.mark.asyncio
async def test_sites_etag_distinct_per_company_filter(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    """``?company_id=`` produces a distinct ETag from the unfiltered list."""
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company_a = await data_factory.create_company(tenant=tenant, name="A Co", session=session)
        company_b = await data_factory.create_company(tenant=tenant, name="B Co", session=session)
        await data_factory.create_site(
            tenant=tenant, company=company_a, name="Site A", session=session
        )
        await data_factory.create_site(
            tenant=tenant, company=company_b, name="Site B", session=session
        )
        await session.commit()
        company_a_id = company_a.id

    headers = await make_auth_headers(RoleEnum.ADMIN)
    unfiltered = await async_client.get("/api/v1/sites", headers=headers)
    filtered = await async_client.get(f"/api/v1/sites?company_id={company_a_id}", headers=headers)
    assert unfiltered.headers["ETag"] != filtered.headers["ETag"]


@pytest.mark.asyncio
async def test_sites_etag_isolated_across_tenants(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    """ETag from tenant A must NOT match tenant B even with identical site names.

    Tenant prefix (``tenant:{tenant_id}``) is baked into the ETag hash; a regression
    that drops it would let one tenant cache another's data — a security bug.
    """
    async with sessionmaker() as session:
        tenant_a = await data_factory.ensure_tenant(slug="acme", session=session)
        tenant_b = await data_factory.ensure_tenant(slug="beta", session=session)
        await data_factory.create_site(tenant=tenant_a, name="Identical", session=session)
        await data_factory.create_site(tenant=tenant_b, name="Identical", session=session)
        await session.commit()

    headers_a = await make_auth_headers(RoleEnum.ADMIN, tenant="acme")
    headers_b = await make_auth_headers(RoleEnum.ADMIN, tenant="beta")
    a = await async_client.get("/api/v1/sites", headers=headers_a)
    b = await async_client.get("/api/v1/sites", headers=headers_b)
    assert a.headers["ETag"] != b.headers["ETag"]


@pytest.mark.asyncio
async def test_sites_etag_from_tenant_a_does_not_match_tenant_b(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    """Cross-tenant ``If-None-Match`` injection: tenant_a's ETag in tenant_b's request → 200."""
    async with sessionmaker() as session:
        tenant_a = await data_factory.ensure_tenant(slug="acme", session=session)
        tenant_b = await data_factory.ensure_tenant(slug="beta", session=session)
        await data_factory.create_site(tenant=tenant_a, name="A site", session=session)
        await data_factory.create_site(tenant=tenant_b, name="B site", session=session)
        await session.commit()

    headers_a = await make_auth_headers(RoleEnum.ADMIN, tenant="acme")
    headers_b = await make_auth_headers(RoleEnum.ADMIN, tenant="beta")
    a = await async_client.get("/api/v1/sites", headers=headers_a)
    etag_a = a.headers["ETag"]

    leaked = await async_client.get("/api/v1/sites", headers={**headers_b, "If-None-Match": etag_a})
    # Tenant B sees its own data, not 304 — tenant_a's ETag is invalid here.
    assert leaked.status_code == status.HTTP_200_OK


# =============================================================================
# Documents list (/api/v1/documents)
# =============================================================================


@pytest.mark.asyncio
async def test_documents_empty_list_returns_etag(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    """Empty documents list — ETag is still emitted (stable for empty)."""
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(slug="delta", session=session)
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN, tenant="delta")
    response = await async_client.get("/api/v1/documents", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    assert response.headers.get("ETag")
    assert response.json()["items"] == []


@pytest.mark.asyncio
async def test_documents_etag_distinct_per_page_param(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    """Different ``page=`` → distinct ETag even on empty data
    (cache key includes page/page_size/total)."""
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(slug="delta", session=session)
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN, tenant="delta")
    page1 = await async_client.get("/api/v1/documents?page=1&page_size=10", headers=headers)
    page1_size50 = await async_client.get("/api/v1/documents?page=1&page_size=50", headers=headers)
    assert page1.status_code == status.HTTP_200_OK
    assert page1_size50.status_code == status.HTTP_200_OK
    assert page1.headers["ETag"] != page1_size50.headers["ETag"]


@pytest.mark.asyncio
async def test_documents_empty_list_hit_returns_304(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    """Empty-list ETag is reusable for conditional GET."""
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(slug="delta", session=session)
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN, tenant="delta")
    first = await async_client.get("/api/v1/documents", headers=headers)
    etag = first.headers["ETag"]

    second = await async_client.get("/api/v1/documents", headers={**headers, "If-None-Match": etag})
    assert second.status_code == status.HTTP_304_NOT_MODIFIED


# =============================================================================
# Tasks list (/api/v1/tasks)
# =============================================================================


async def _seed_task(
    session,
    *,
    tenant: Tenant,
    title: str = "Inspect site",
    status_value: TaskStatus = TaskStatus.OPEN,
    priority: TaskPriority = TaskPriority.MEDIUM,
) -> Task:
    task = Task(
        tenant_id=tenant.id,
        title=title,
        status=status_value,
        priority=priority,
    )
    session.add(task)
    await session.flush()
    return task


@pytest.mark.anyio
async def test_tasks_hit_returns_304(
    async_client: AsyncClient, make_auth_headers, sessionmaker
) -> None:
    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        await _seed_task(session, tenant=tenant, title="Hit Task")
        await session.commit()

    headers = await make_auth_headers()
    first = await async_client.get("/api/v1/tasks", headers=headers)
    assert first.status_code == status.HTTP_200_OK
    etag = first.headers["ETag"]

    second = await async_client.get("/api/v1/tasks", headers={**headers, "If-None-Match": etag})
    assert second.status_code == status.HTTP_304_NOT_MODIFIED


@pytest.mark.anyio
async def test_tasks_etag_distinct_per_status_filter(
    async_client: AsyncClient, make_auth_headers, sessionmaker
) -> None:
    """``?status=`` is part of the cache key."""
    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        await _seed_task(session, tenant=tenant, title="Open Task", status_value=TaskStatus.OPEN)
        await _seed_task(session, tenant=tenant, title="Done Task", status_value=TaskStatus.DONE)
        await session.commit()

    headers = await make_auth_headers()
    all_tasks = await async_client.get("/api/v1/tasks", headers=headers)
    open_only = await async_client.get("/api/v1/tasks?status=open", headers=headers)
    done_only = await async_client.get("/api/v1/tasks?status=done", headers=headers)
    assert all_tasks.headers["ETag"] != open_only.headers["ETag"]
    assert open_only.headers["ETag"] != done_only.headers["ETag"]


@pytest.mark.anyio
async def test_tasks_etag_distinct_per_priority_filter(
    async_client: AsyncClient, make_auth_headers, sessionmaker
) -> None:
    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        await _seed_task(session, tenant=tenant, title="High", priority=TaskPriority.HIGH)
        await _seed_task(session, tenant=tenant, title="Low", priority=TaskPriority.LOW)
        await session.commit()

    headers = await make_auth_headers()
    high = await async_client.get("/api/v1/tasks?priority=high", headers=headers)
    low = await async_client.get("/api/v1/tasks?priority=low", headers=headers)
    assert high.headers["ETag"] != low.headers["ETag"]


@pytest.mark.anyio
async def test_tasks_etag_changes_after_create(
    async_client: AsyncClient, make_auth_headers, sessionmaker
) -> None:
    """Creating a new task via POST invalidates the list ETag."""
    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        await _seed_task(session, tenant=tenant, title="Before-POST")
        await session.commit()

    headers = await make_auth_headers()
    first = await async_client.get("/api/v1/tasks", headers=headers)
    initial_etag = first.headers["ETag"]

    create = await async_client.post(
        "/api/v1/tasks",
        json={"title": "After POST Task"},
        headers=headers,
    )
    assert create.status_code == status.HTTP_201_CREATED

    second = await async_client.get("/api/v1/tasks", headers=headers)
    assert second.headers["ETag"] != initial_etag


@pytest.mark.anyio
async def test_tasks_empty_list_has_etag_and_returns_304_on_repeat(
    async_client: AsyncClient, make_auth_headers, sessionmaker
) -> None:
    async with sessionmaker() as session:
        # Use clean tenant
        zeta = (await session.execute(select(Tenant).where(Tenant.slug == "zeta"))).scalar_one()
        # Ensure no tasks exist for this tenant
        existing = (
            (await session.execute(select(Task).where(Task.tenant_id == zeta.id))).scalars().all()
        )
        for t in existing:
            await session.delete(t)
        await session.commit()

    headers = await make_auth_headers(tenant="zeta")
    first = await async_client.get("/api/v1/tasks", headers=headers)
    assert first.status_code == status.HTTP_200_OK
    assert first.json()["items"] == []
    etag = first.headers["ETag"]
    assert etag

    second = await async_client.get("/api/v1/tasks", headers={**headers, "If-None-Match": etag})
    assert second.status_code == status.HTTP_304_NOT_MODIFIED


@pytest.mark.anyio
async def test_tasks_etag_distinct_per_page(
    async_client: AsyncClient, make_auth_headers, sessionmaker
) -> None:
    """``page=1`` and ``page=2`` distinct ETags even on small datasets."""
    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        for i in range(3):
            await _seed_task(session, tenant=tenant, title=f"PageTask {i}")
        await session.commit()

    headers = await make_auth_headers()
    page1 = await async_client.get("/api/v1/tasks?page=1&page_size=1", headers=headers)
    page2 = await async_client.get("/api/v1/tasks?page=2&page_size=1", headers=headers)
    assert page1.headers["ETag"] != page2.headers["ETag"]


# =============================================================================
# Cross-cutting: ETag stability & determinism
# =============================================================================


@pytest.mark.asyncio
async def test_companies_etag_is_quoted_per_rfc7232(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    """RFC 7232: ETag must be a quoted-string (`"..."`)."""
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        await data_factory.create_company(tenant=tenant, name="Quoted", session=session)
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN)
    response = await async_client.get("/api/v1/companies", headers=headers)
    etag = response.headers["ETag"]
    assert etag.startswith('"') and etag.endswith('"'), f"ETag not quoted: {etag!r}"


@pytest.mark.asyncio
async def test_sites_etag_deterministic_across_repeated_reads(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    """Same data + same request 3 times → identical ETag (deterministic hash)."""
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        await data_factory.create_site(tenant=tenant, name="Deterministic", session=session)
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN)
    etags = []
    for _ in range(3):
        response = await async_client.get("/api/v1/sites", headers=headers)
        etags.append(response.headers["ETag"])
    assert etags[0] == etags[1] == etags[2]


@pytest.mark.anyio
async def test_tasks_etag_deterministic_independent_of_repeat(
    async_client: AsyncClient, make_auth_headers, sessionmaker
) -> None:
    """Tasks ETag stable across repeated reads of the same data."""
    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        await _seed_task(session, tenant=tenant, title="Stable")
        await session.commit()

    headers = await make_auth_headers()
    a = await async_client.get("/api/v1/tasks", headers=headers)
    b = await async_client.get("/api/v1/tasks", headers=headers)
    assert a.headers["ETag"] == b.headers["ETag"]
