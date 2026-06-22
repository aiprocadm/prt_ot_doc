"""HTTP cache (ETag / If-None-Match) contract for /api/v1/risk/cards +
/api/v1/risk/action-plans (Phase 9.2 extension / vNext-PERF-03, Session 56).

Continues the S53→S55 rollout. Two flat-list endpoints:

- ``/risk/cards`` — stored summaries of risk assessments. Six optional filters
  (assessment/company/site/workplace/position/employee), no pagination.
- ``/risk/action-plans`` — mitigation plans per assessment. Same six filter
  axes.

Neither has a public POST endpoint — both are created internally by
``/risk/assess`` along with their parent ``RiskAssessment``. Tests therefore
use direct ORM seeding (proven pattern from S53 medical/exams + S55 risk/maps).

After S56, coverage extends to 23 list endpoints carrying ETag conditional-GET.

Pinned axes: hit/miss/filter isolation/empty-stable.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi import status
from httpx import AsyncClient

from app.models.models import RoleEnum
from app.models.risk import RiskActionPlan, RiskAssessment, RiskCard, RiskHazard
from tests.utils.factories import TestDataFactory

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------


async def _seed_risk_chain(
    session,
    *,
    tenant_id: str,
    company_id: str | None = None,
    hazard_code_suffix: str | None = None,
) -> tuple[str, str, str]:
    """Seed full chain: hazard + assessment + card + action_plan.

    Returns ``(assessment_id, card_id, action_plan_id)``.
    """
    code = hazard_code_suffix or uuid.uuid4().hex[:8]
    hazard = RiskHazard(
        tenant_id=tenant_id,
        code=f"hzd-{code}",
        title=f"Hazard {code}",
    )
    session.add(hazard)
    await session.flush()

    assessment = RiskAssessment(
        tenant_id=tenant_id,
        hazard_id=hazard.id,
        company_id=company_id,
        severity_before=3,
        likelihood_before=2,
        score_before=6,
        band_before="med",
        severity_after=2,
        likelihood_after=1,
        score_after=2,
        band_after="low",
    )
    session.add(assessment)
    await session.flush()

    card = RiskCard(
        tenant_id=tenant_id,
        assessment_id=assessment.id,
        company_id=company_id,
        summary={"seeded": True},
    )
    session.add(card)

    plan = RiskActionPlan(
        tenant_id=tenant_id,
        assessment_id=assessment.id,
        company_id=company_id,
        status="open",
    )
    session.add(plan)

    await session.flush()
    return assessment.id, card.id, plan.id


# =============================================================================
# /api/v1/risk/cards
# =============================================================================


@pytest.mark.asyncio
async def test_risk_cards_hit_returns_304(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        await _seed_risk_chain(session, tenant_id=str(tenant.id), company_id=str(company.id))
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN)
    first = await async_client.get("/api/v1/risk/cards", headers=headers)
    assert first.status_code == status.HTTP_200_OK
    etag = first.headers["ETag"]

    second = await async_client.get(
        "/api/v1/risk/cards", headers={**headers, "If-None-Match": etag}
    )
    assert second.status_code == status.HTTP_304_NOT_MODIFIED
    assert second.headers["ETag"] == etag
    assert second.content == b""


@pytest.mark.asyncio
async def test_risk_cards_miss_with_bogus_etag(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        await _seed_risk_chain(session, tenant_id=str(tenant.id), company_id=str(company.id))
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN)
    response = await async_client.get(
        "/api/v1/risk/cards", headers={**headers, "If-None-Match": '"stale-card"'}
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()


@pytest.mark.asyncio
async def test_risk_cards_etag_distinct_per_company_filter(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company_a = await data_factory.create_company(tenant=tenant, name="A Co", session=session)
        company_b = await data_factory.create_company(tenant=tenant, name="B Co", session=session)
        await _seed_risk_chain(
            session,
            tenant_id=str(tenant.id),
            company_id=str(company_a.id),
            hazard_code_suffix="a",
        )
        await _seed_risk_chain(
            session,
            tenant_id=str(tenant.id),
            company_id=str(company_b.id),
            hazard_code_suffix="b",
        )
        await session.commit()
        company_a_id = str(company_a.id)

    headers = await make_auth_headers(RoleEnum.ADMIN)
    unfiltered = await async_client.get("/api/v1/risk/cards", headers=headers)
    filtered = await async_client.get(
        f"/api/v1/risk/cards?company_id={company_a_id}", headers=headers
    )
    assert unfiltered.headers["ETag"] != filtered.headers["ETag"]


@pytest.mark.asyncio
async def test_risk_cards_etag_distinct_per_assessment_filter(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        assessment_a, _, _ = await _seed_risk_chain(
            session,
            tenant_id=str(tenant.id),
            company_id=str(company.id),
            hazard_code_suffix="ax",
        )
        await _seed_risk_chain(
            session,
            tenant_id=str(tenant.id),
            company_id=str(company.id),
            hazard_code_suffix="bx",
        )
        await session.commit()
        assessment_a_id = str(assessment_a)

    headers = await make_auth_headers(RoleEnum.ADMIN)
    unfiltered = await async_client.get("/api/v1/risk/cards", headers=headers)
    filtered = await async_client.get(
        f"/api/v1/risk/cards?assessment_id={assessment_a_id}", headers=headers
    )
    assert unfiltered.headers["ETag"] != filtered.headers["ETag"]


@pytest.mark.asyncio
async def test_risk_cards_empty_list_stable_etag(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(slug="cards-empty", session=session)
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN, tenant="cards-empty")
    first = await async_client.get("/api/v1/risk/cards", headers=headers)
    assert first.status_code == status.HTTP_200_OK
    assert first.json() == []
    etag = first.headers["ETag"]
    assert etag

    second = await async_client.get(
        "/api/v1/risk/cards", headers={**headers, "If-None-Match": etag}
    )
    assert second.status_code == status.HTTP_304_NOT_MODIFIED


# =============================================================================
# /api/v1/risk/action-plans
# =============================================================================


@pytest.mark.asyncio
async def test_risk_action_plans_hit_returns_304(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        await _seed_risk_chain(session, tenant_id=str(tenant.id), company_id=str(company.id))
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN)
    first = await async_client.get("/api/v1/risk/action-plans", headers=headers)
    assert first.status_code == status.HTTP_200_OK
    etag = first.headers["ETag"]

    second = await async_client.get(
        "/api/v1/risk/action-plans", headers={**headers, "If-None-Match": etag}
    )
    assert second.status_code == status.HTTP_304_NOT_MODIFIED
    assert second.headers["ETag"] == etag
    assert second.content == b""


@pytest.mark.asyncio
async def test_risk_action_plans_miss_with_bogus_etag(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        await _seed_risk_chain(session, tenant_id=str(tenant.id), company_id=str(company.id))
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN)
    response = await async_client.get(
        "/api/v1/risk/action-plans",
        headers={**headers, "If-None-Match": '"stale-plan"'},
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()


@pytest.mark.asyncio
async def test_risk_action_plans_etag_distinct_per_assessment_filter(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        assessment_a, _, _ = await _seed_risk_chain(
            session,
            tenant_id=str(tenant.id),
            company_id=str(company.id),
            hazard_code_suffix="pa",
        )
        await _seed_risk_chain(
            session,
            tenant_id=str(tenant.id),
            company_id=str(company.id),
            hazard_code_suffix="pb",
        )
        await session.commit()
        assessment_a_id = str(assessment_a)

    headers = await make_auth_headers(RoleEnum.ADMIN)
    unfiltered = await async_client.get("/api/v1/risk/action-plans", headers=headers)
    filtered = await async_client.get(
        f"/api/v1/risk/action-plans?assessment_id={assessment_a_id}", headers=headers
    )
    assert unfiltered.headers["ETag"] != filtered.headers["ETag"]


@pytest.mark.asyncio
async def test_risk_action_plans_empty_list_stable_etag(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(slug="plans-empty", session=session)
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN, tenant="plans-empty")
    first = await async_client.get("/api/v1/risk/action-plans", headers=headers)
    assert first.status_code == status.HTTP_200_OK
    assert first.json() == []
    etag = first.headers["ETag"]
    assert etag

    second = await async_client.get(
        "/api/v1/risk/action-plans", headers={**headers, "If-None-Match": etag}
    )
    assert second.status_code == status.HTTP_304_NOT_MODIFIED
