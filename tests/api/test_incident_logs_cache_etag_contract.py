"""HTTP cache (ETag / If-None-Match) contract for /api/v1/incidents/{id}/logs
(Phase 9.3 / vNext-PERF-03, Session 58).

First **sub-resource** list endpoint to carry an ETag. Unlike the flat lists
hardened in Sessions 47-57, the cache key here must include the parent
``incident_id`` scalar — otherwise two incidents within the same tenant
could hand each other's clients a 304 by coincidence.

The endpoint has no filters and no pagination, so the cache key reduces to
``(tenant_id, ("incident", incident_id), rows*)``. We pin:

- hit/miss/bogus axes (parity with the flat-list contracts)
- **parent isolation** — distinct ETags per incident_id (the new axis)
- mutation invalidation — appending a log changes the ETag
- empty list still emits a stable ETag (304 supported even with no rows)
- cross-tenant isolation — same incident shape across tenants → distinct
  ETags (defends the leading ``tenant:`` part of the hash)

After S58, ETag coverage extends to **25 list endpoints** (24 flat + 1
parent-scoped sub-resource).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import status
from httpx import AsyncClient

from app.models.models import (
    Incident,
    IncidentLog,
    IncidentSeverity,
    IncidentStage,
    IncidentStatus,
    IncidentType,
    RoleEnum,
)
from tests.utils.factories import TestDataFactory


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------


async def _seed_incident(
    session,
    *,
    tenant_id: str,
    company_id: str,
    site_id: str,
    title: str = "Падение груза",
    occurred_at: datetime | None = None,
) -> Incident:
    """Direct ORM seed — sidesteps register_incident() side-effects
    (outbox/audit) we don't need for cache contract tests."""
    incident = Incident(
        tenant_id=tenant_id,
        company_id=company_id,
        site_id=site_id,
        title=title,
        incident_type=IncidentType.ACCIDENT,
        severity=IncidentSeverity.LOW,
        status=IncidentStatus.INVESTIGATING,
        occurred_at=occurred_at or datetime.now(timezone.utc),
    )
    session.add(incident)
    await session.flush()
    return incident


async def _seed_log(
    session,
    *,
    tenant_id: str,
    incident_id: str,
    message: str = "Назначена комиссия",
    stage: IncidentStage = IncidentStage.INVESTIGATION,
    status_: IncidentStatus = IncidentStatus.INVESTIGATING,
    created_at: datetime | None = None,
) -> IncidentLog:
    log = IncidentLog(
        tenant_id=tenant_id,
        incident_id=incident_id,
        stage=stage,
        status=status_,
        message=message,
        metadata_json={},
    )
    if created_at is not None:
        log.created_at = created_at
    session.add(log)
    await session.flush()
    return log


# =============================================================================
# /api/v1/incidents/{id}/logs — basic conditional GET
# =============================================================================


@pytest.mark.asyncio
async def test_incident_logs_hit_returns_304(
    async_client: AsyncClient,
    make_auth_headers,
    sessionmaker,
    data_factory: TestDataFactory,
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        site = await data_factory.create_site(tenant=tenant, company=company, session=session)
        incident = await _seed_incident(
            session, tenant_id=str(tenant.id), company_id=str(company.id), site_id=str(site.id)
        )
        await _seed_log(session, tenant_id=str(tenant.id), incident_id=str(incident.id))
        await session.commit()
        incident_id = str(incident.id)

    headers = await make_auth_headers(RoleEnum.ADMIN)
    first = await async_client.get(
        f"/api/v1/incidents/{incident_id}/logs", headers=headers
    )
    assert first.status_code == status.HTTP_200_OK
    etag = first.headers["ETag"]
    assert etag

    second = await async_client.get(
        f"/api/v1/incidents/{incident_id}/logs",
        headers={**headers, "If-None-Match": etag},
    )
    assert second.status_code == status.HTTP_304_NOT_MODIFIED
    assert second.headers["ETag"] == etag
    assert second.content == b""


@pytest.mark.asyncio
async def test_incident_logs_miss_with_bogus_etag(
    async_client: AsyncClient,
    make_auth_headers,
    sessionmaker,
    data_factory: TestDataFactory,
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        site = await data_factory.create_site(tenant=tenant, company=company, session=session)
        incident = await _seed_incident(
            session, tenant_id=str(tenant.id), company_id=str(company.id), site_id=str(site.id)
        )
        await _seed_log(session, tenant_id=str(tenant.id), incident_id=str(incident.id))
        await session.commit()
        incident_id = str(incident.id)

    headers = await make_auth_headers(RoleEnum.ADMIN)
    response = await async_client.get(
        f"/api/v1/incidents/{incident_id}/logs",
        headers={**headers, "If-None-Match": '"stale-log"'},
    )
    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert isinstance(body, list) and len(body) == 1


# =============================================================================
# Parent isolation — the sub-resource axis
# =============================================================================


@pytest.mark.asyncio
async def test_incident_logs_etag_distinct_per_parent_incident(
    async_client: AsyncClient,
    make_auth_headers,
    sessionmaker,
    data_factory: TestDataFactory,
) -> None:
    """Two incidents within the same tenant must produce different ETags
    even when their log lists happen to be identical in shape — the parent
    incident_id must participate in the cache key.
    """
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        site = await data_factory.create_site(tenant=tenant, company=company, session=session)
        incident_a = await _seed_incident(
            session,
            tenant_id=str(tenant.id),
            company_id=str(company.id),
            site_id=str(site.id),
            title="A",
        )
        incident_b = await _seed_incident(
            session,
            tenant_id=str(tenant.id),
            company_id=str(company.id),
            site_id=str(site.id),
            title="B",
        )
        # Identical log payload on both — proves the parent_id is what
        # distinguishes the cache key.
        await _seed_log(session, tenant_id=str(tenant.id), incident_id=str(incident_a.id))
        await _seed_log(session, tenant_id=str(tenant.id), incident_id=str(incident_b.id))
        await session.commit()
        a_id, b_id = str(incident_a.id), str(incident_b.id)

    headers = await make_auth_headers(RoleEnum.ADMIN)
    resp_a = await async_client.get(f"/api/v1/incidents/{a_id}/logs", headers=headers)
    resp_b = await async_client.get(f"/api/v1/incidents/{b_id}/logs", headers=headers)
    assert resp_a.status_code == status.HTTP_200_OK
    assert resp_b.status_code == status.HTTP_200_OK
    assert resp_a.headers["ETag"] != resp_b.headers["ETag"]

    # Critically: ETag from incident A must NOT 304 a request on incident B.
    cross = await async_client.get(
        f"/api/v1/incidents/{b_id}/logs",
        headers={**headers, "If-None-Match": resp_a.headers["ETag"]},
    )
    assert cross.status_code == status.HTTP_200_OK


# =============================================================================
# Mutation invalidates
# =============================================================================


@pytest.mark.asyncio
async def test_incident_logs_etag_changes_after_new_log(
    async_client: AsyncClient,
    make_auth_headers,
    sessionmaker,
    data_factory: TestDataFactory,
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        site = await data_factory.create_site(tenant=tenant, company=company, session=session)
        incident = await _seed_incident(
            session, tenant_id=str(tenant.id), company_id=str(company.id), site_id=str(site.id)
        )
        await _seed_log(
            session,
            tenant_id=str(tenant.id),
            incident_id=str(incident.id),
            message="first",
            created_at=datetime.now(timezone.utc) - timedelta(minutes=5),
        )
        await session.commit()
        incident_id = str(incident.id)

    headers = await make_auth_headers(RoleEnum.ADMIN)
    before = await async_client.get(
        f"/api/v1/incidents/{incident_id}/logs", headers=headers
    )
    assert before.status_code == status.HTTP_200_OK
    etag_before = before.headers["ETag"]

    # Append a log via the public POST — exercises the write path,
    # not just direct ORM seeding.
    new_log = await async_client.post(
        f"/api/v1/incidents/{incident_id}/logs",
        json={
            "stage": IncidentStage.INVESTIGATION.value,
            "status": IncidentStatus.INVESTIGATING.value,
            "message": "second",
            "metadata_json": {},
        },
        headers=headers,
    )
    assert new_log.status_code == status.HTTP_201_CREATED

    after = await async_client.get(
        f"/api/v1/incidents/{incident_id}/logs", headers=headers
    )
    assert after.status_code == status.HTTP_200_OK
    assert after.headers["ETag"] != etag_before


# =============================================================================
# Empty list still emits ETag
# =============================================================================


@pytest.mark.asyncio
async def test_incident_logs_empty_list_stable_etag(
    async_client: AsyncClient,
    make_auth_headers,
    sessionmaker,
    data_factory: TestDataFactory,
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        site = await data_factory.create_site(tenant=tenant, company=company, session=session)
        incident = await _seed_incident(
            session, tenant_id=str(tenant.id), company_id=str(company.id), site_id=str(site.id)
        )
        await session.commit()
        incident_id = str(incident.id)

    headers = await make_auth_headers(RoleEnum.ADMIN)
    first = await async_client.get(
        f"/api/v1/incidents/{incident_id}/logs", headers=headers
    )
    assert first.status_code == status.HTTP_200_OK
    assert first.json() == []
    etag = first.headers["ETag"]
    assert etag

    second = await async_client.get(
        f"/api/v1/incidents/{incident_id}/logs",
        headers={**headers, "If-None-Match": etag},
    )
    assert second.status_code == status.HTTP_304_NOT_MODIFIED


# =============================================================================
# Cross-tenant isolation — defends the tenant: prefix in the hash
# =============================================================================


@pytest.mark.asyncio
async def test_incident_logs_etag_isolated_cross_tenant(
    async_client: AsyncClient,
    make_auth_headers,
    sessionmaker,
    data_factory: TestDataFactory,
) -> None:
    """Same parent-id collisions across tenants must NOT produce the same
    ETag. The leading ``tenant:`` part of the hash defends this; the test
    pins that defence.
    """
    async with sessionmaker() as session:
        tenant_x = await data_factory.ensure_tenant(slug="logs-x", session=session)
        company_x = await data_factory.create_company(tenant=tenant_x, session=session)
        site_x = await data_factory.create_site(tenant=tenant_x, company=company_x, session=session)
        incident_x = await _seed_incident(
            session,
            tenant_id=str(tenant_x.id),
            company_id=str(company_x.id),
            site_id=str(site_x.id),
        )
        await _seed_log(
            session,
            tenant_id=str(tenant_x.id),
            incident_id=str(incident_x.id),
            message="payload",
        )

        tenant_y = await data_factory.ensure_tenant(slug="logs-y", session=session)
        company_y = await data_factory.create_company(tenant=tenant_y, session=session)
        site_y = await data_factory.create_site(tenant=tenant_y, company=company_y, session=session)
        incident_y = await _seed_incident(
            session,
            tenant_id=str(tenant_y.id),
            company_id=str(company_y.id),
            site_id=str(site_y.id),
        )
        await _seed_log(
            session,
            tenant_id=str(tenant_y.id),
            incident_id=str(incident_y.id),
            message="payload",
        )
        await session.commit()
        x_id, y_id = str(incident_x.id), str(incident_y.id)

    # Distinct emails per tenant — bypass make_auth_headers SELECT-by-email
    # collision documented in S55 handoff.
    headers_x = await make_auth_headers(
        RoleEnum.ADMIN, tenant="logs-x", email="admin-x@example.com"
    )
    headers_y = await make_auth_headers(
        RoleEnum.ADMIN, tenant="logs-y", email="admin-y@example.com"
    )

    resp_x = await async_client.get(
        f"/api/v1/incidents/{x_id}/logs", headers=headers_x
    )
    resp_y = await async_client.get(
        f"/api/v1/incidents/{y_id}/logs", headers=headers_y
    )
    assert resp_x.status_code == status.HTTP_200_OK
    assert resp_y.status_code == status.HTTP_200_OK
    assert resp_x.headers["ETag"] != resp_y.headers["ETag"]
