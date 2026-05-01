import pytest
from sqlalchemy import select

from app.models.models import RoleEnum, Site, Tenant
from app.models.risk import (
    RiskActionPlan,
    RiskActionPlanItem,
    RiskAssessment,
    RiskAssessmentItem,
    RiskCard,
)


@pytest.mark.anyio
async def test_risk_assessment_artifacts_and_idempotency(
    async_client, make_auth_headers, sessionmaker, data_factory
) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)

    methodology_resp = await async_client.post(
        "/api/v1/risk/methodologies",
        json={
            "name": "KPI-5 Matrix",
            "bands": [
                {"name": "low", "max": 4},
                {"name": "med", "max": 8},
                {"name": "high", "max": 12},
                {"name": "crit", "max": 25},
            ],
        },
        headers=headers,
    )
    assert methodology_resp.status_code == 200, methodology_resp.text
    methodology_id = methodology_resp.json()["id"]

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(
            tenant=tenant, session=session, name="Plan Corp"
        )
        site = Site(tenant_id=tenant.id, company_id=company.id, name="Main Site")
        session.add(site)
        await session.commit()
        await session.refresh(site)
        company_id = company.id
        site_id = site.id

    hazard_payloads = [
        {
            "code": "chem",
            "title": "Chemical exposure",
            "module": "ot",
            "recommended_measures": [{"text": "Provide respirator", "due_in_days": 10}],
        },
        {
            "code": "noise",
            "title": "Excessive noise",
            "module": "ot",
            "recommended_measures": [{"text": "Install dampers", "due_in_days": 20}],
        },
    ]
    for payload in hazard_payloads:
        hazard_resp = await async_client.post(
            "/api/v1/risk/hazards", json=payload, headers=headers
        )
        assert hazard_resp.status_code == 200, hazard_resp.text

    assess_payload = {
        "company_id": company_id,
        "place_id": site_id,
        "methodology_id": methodology_id,
        "assessment_key": "kpi5-assessment",
        "assessment_version": 1,
        "items": [
            {"hazard_code": "chem", "probability": 2, "severity": 3},
            {"hazard_code": "noise", "probability": 4, "severity": 2},
        ],
    }
    assess_resp = await async_client.post(
        "/api/v1/risk/assess",
        json=assess_payload,
        headers={**headers, "Idempotency-Key": "kpi5-idem-1"},
    )
    assert assess_resp.status_code == 200, assess_resp.text
    body = assess_resp.json()
    assessment_id = body["assessment_id"]

    idempotent_resp = await async_client.post(
        "/api/v1/risk/assess",
        json=assess_payload,
        headers={**headers, "Idempotency-Key": "kpi5-idem-1"},
    )
    assert idempotent_resp.status_code == 200, idempotent_resp.text
    assert idempotent_resp.json()["assessment_id"] == assessment_id

    async with sessionmaker() as session:
        tenant = (
            await session.execute(select(Tenant).where(Tenant.slug == "test"))
        ).scalar_one()
        tenant_id = str(tenant.id)

        assessments = (
            await session.execute(
                select(RiskAssessment).where(
                    RiskAssessment.tenant_id == tenant_id,
                    RiskAssessment.assessment_key == "kpi5-assessment",
                )
            )
        ).scalars().all()
        assert len(assessments) == 1

        items = (
            await session.execute(
                select(RiskAssessmentItem).where(
                    RiskAssessmentItem.tenant_id == tenant_id,
                    RiskAssessmentItem.assessment_id == assessment_id,
                )
            )
        ).scalars().all()
        assert len(items) == 2
        assert {item.level for item in items} == {"med"}

        risk_cards = (
            await session.execute(
                select(RiskCard).where(
                    RiskCard.tenant_id == tenant_id,
                    RiskCard.assessment_id == assessment_id,
                )
            )
        ).scalars().all()
        assert len(risk_cards) == 1

        action_plan = (
            await session.execute(
                select(RiskActionPlan).where(
                    RiskActionPlan.tenant_id == tenant_id,
                    RiskActionPlan.assessment_id == assessment_id,
                )
            )
        ).scalar_one()
        action_items = (
            await session.execute(
                select(RiskActionPlanItem).where(
                    RiskActionPlanItem.tenant_id == tenant_id,
                    RiskActionPlanItem.plan_id == action_plan.id,
                )
            )
        ).scalars().all()
        assert len(action_items) == 2


@pytest.mark.anyio
async def test_risk_assessment_emits_riskassessed_outbox_event(
    async_client, make_auth_headers, sessionmaker, data_factory
) -> None:
    """
    Test that risk assessment emits RiskAssessed event to outbox (TZ-3.1-MVP-01).

    This verifies the mandatory event emission required for risk domain.
    """
    from app.models.models import Outbox

    headers = await make_auth_headers(RoleEnum.ADMIN)

    methodology_resp = await async_client.post(
        "/api/v1/risk/methodologies",
        json={
            "name": "Event Test Matrix",
            "bands": [
                {"name": "low", "max": 4},
                {"name": "high", "max": 25},
            ],
        },
        headers=headers,
    )
    assert methodology_resp.status_code == 200, methodology_resp.text
    methodology_id = methodology_resp.json()["id"]

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(
            tenant=tenant, session=session, name="Risk Event Corp"
        )
        site = Site(tenant_id=tenant.id, company_id=company.id, name="Event Site")
        session.add(site)
        await session.commit()
        await session.refresh(site)
        company_id = company.id
        site_id = site.id
        tenant_id = str(tenant.id)

    hazard_resp = await async_client.post(
        "/api/v1/risk/hazards",
        json={"code": "test-hazard", "title": "Test Hazard", "module": "ot"},
        headers=headers,
    )
    assert hazard_resp.status_code == 200, hazard_resp.text

    assess_payload = {
        "company_id": company_id,
        "place_id": site_id,
        "methodology_id": methodology_id,
        "assessment_key": "event-test-assessment",
        "assessment_version": 1,
        "items": [
            {"hazard_code": "test-hazard", "probability": 3, "severity": 3},
        ],
    }
    assess_resp = await async_client.post(
        "/api/v1/risk/assess",
        json=assess_payload,
        headers=headers,
    )
    assert assess_resp.status_code == 200, assess_resp.text
    assessment_id = assess_resp.json()["assessment_id"]

    # Verify RiskAssessed event was emitted to outbox
    async with sessionmaker() as session:
        outbox_entry = (
            await session.execute(
                select(Outbox).where(
                    Outbox.tenant_id == tenant_id,
                    Outbox.event_type == "RiskAssessed",
                )
            )
        ).scalar_one_or_none()

        assert outbox_entry is not None, "RiskAssessed event not emitted to outbox"
        assert outbox_entry.destination is not None or outbox_entry.event_type == "RiskAssessed"
        assert outbox_entry.payload is not None
        payload = outbox_entry.payload
        assert payload.get("assessment_id") == assessment_id


@pytest.mark.anyio
async def test_risk_assessment_versioning_and_tenant_isolation(
    async_client, make_auth_headers, sessionmaker, data_factory
) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)

    methodology_resp = await async_client.post(
        "/api/v1/risk/methodologies",
        json={"name": "Versioned Matrix", "bands": [{"name": "low", "max": 25}]},
        headers=headers,
    )
    assert methodology_resp.status_code == 200, methodology_resp.text
    methodology_id = methodology_resp.json()["id"]

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(
            tenant=tenant, session=session, name="Version Corp"
        )
        site = Site(tenant_id=tenant.id, company_id=company.id, name="Scope Site")
        session.add(site)
        await session.commit()
        await session.refresh(site)
        company_id = company.id
        site_id = site.id

    hazard_resp = await async_client.post(
        "/api/v1/risk/hazards",
        json={"code": "fall", "title": "Fall risk", "module": "ot"},
        headers=headers,
    )
    assert hazard_resp.status_code == 200, hazard_resp.text

    base_payload = {
        "company_id": company_id,
        "place_id": site_id,
        "methodology_id": methodology_id,
        "assessment_key": "versioned-assessment",
        "items": [{"hazard_code": "fall", "probability": 5, "severity": 5}],
    }
    first_resp = await async_client.post(
        "/api/v1/risk/assess",
        json={**base_payload, "assessment_version": 1},
        headers=headers,
    )
    assert first_resp.status_code == 200, first_resp.text
    second_resp = await async_client.post(
        "/api/v1/risk/assess",
        json={**base_payload, "assessment_version": 2},
        headers=headers,
    )
    assert second_resp.status_code == 200, second_resp.text
    assert first_resp.json()["assessment_id"] != second_resp.json()["assessment_id"]

    other_tenant_headers = {**headers, "x-tenant": "acme"}
    not_found = await async_client.get(
        f"/api/v1/risk/assessments/{first_resp.json()['assessment_id']}",
        headers=other_tenant_headers,
    )
    assert not_found.status_code == 403
