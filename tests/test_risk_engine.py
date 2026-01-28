import json

import pytest
from sqlalchemy import select

from app.models.models import Outbox, Position, RiskMap, RoleEnum, Site, Tenant
from app.models.risk import (
    RiskActionPlan,
    RiskActionPlanItem,
    RiskAssessment,
    RiskAssessmentItem,
    RiskCard,
    RiskHazard,
    RiskMatrixCell,
)


@pytest.mark.anyio
async def test_risk_engine_flow(
    async_client, make_auth_headers, sessionmaker, data_factory
) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)

    methodology_payload = {
        "name": "3x3 matrix",
        "severity_scale": [
            {"value": 1, "label": "Minor"},
            {"value": 2, "label": "Major"},
            {"value": 3, "label": "Critical"},
        ],
        "likelihood_scale": [
            {"value": 1, "label": "Rare"},
            {"value": 2, "label": "Possible"},
            {"value": 3, "label": "Likely"},
        ],
        "bands": [
            {"name": "low", "max": 3},
            {"name": "med", "max": 6},
            {"name": "high", "max": 9},
            {"name": "crit", "max": 12},
        ],
    }
    methodology_resp = await async_client.post(
        "/api/v1/risk/methodologies", json=methodology_payload, headers=headers
    )
    assert methodology_resp.status_code == 200, methodology_resp.text
    methodology_id = methodology_resp.json()["id"]

    response = await async_client.put(
        "/api/v1/risk/matrix",
        json={"rows": [], "methodology_id": methodology_id},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["ok"] is True
    assert payload["count"] == 9

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(
            tenant=tenant, session=session, name="Risk Corp"
        )
        site = Site(tenant_id=tenant.id, company_id=company.id, name="Site A")
        position = Position(
            tenant_id=tenant.id, company_id=company.id, name="Inspector"
        )
        session.add_all([site, position])
        await session.commit()
        await session.refresh(site)
        await session.refresh(position)
        company_id = company.id
        site_id = site.id
        position_id = position.id

    hazard_payload = {
        "code": "work_height",
        "title": "Работы на высоте",
        "module": "ot",
    }
    hazard_resp = await async_client.post(
        "/api/v1/risk/hazards",
        json=hazard_payload,
        headers=headers,
    )
    assert hazard_resp.status_code == 200, hazard_resp.text
    hazard_id = hazard_resp.json()["id"]

    control_resp = await async_client.post(
        "/api/v1/risk/controls",
        json={"code": "harness", "title": "Привязь", "type": "ppe"},
        headers=headers,
    )
    assert control_resp.status_code == 200, control_resp.text

    assess_payload = {
        "company_id": company_id,
        "place_id": site_id,
        "position_id": position_id,
        "job_title": "монтажник",
        "hazard_code": "work_height",
        "before": [3, 3],
        "controls": ["harness"],
        "created_by": "inspector-77",
    }
    assess_resp = await async_client.post(
        "/api/v1/risk/assess",
        json=assess_payload,
        headers=headers,
    )
    assert assess_resp.status_code == 200, assess_resp.text
    assessment_body = assess_resp.json()
    assessment_id = assessment_body["assessment_id"]

    assert assessment_body["risk_card_ids"]
    assert assessment_body["action_plan_id"]

    risk_map_resp = await async_client.post(
        "/api/v1/risk/maps",
        json={
            "methodology_id": methodology_id,
            "company_id": company_id,
            "site_id": site_id,
            "position_id": position_id,
        },
        headers=headers,
    )
    assert risk_map_resp.status_code == 200, risk_map_resp.text
    risk_map_payload = risk_map_resp.json()
    assert risk_map_payload["matrix"]["total_assessments"] == 1

    list_resp = await async_client.get(
        "/api/v1/risk/maps",
        params={
            "company_id": company_id,
            "site_id": site_id,
            "position_id": position_id,
            "methodology_id": methodology_id,
        },
        headers=headers,
    )
    assert list_resp.status_code == 200, list_resp.text
    maps = list_resp.json()
    assert len(maps) == 1

    async with sessionmaker() as session:
        tenant = (
            await session.execute(select(Tenant).where(Tenant.slug == "test"))
        ).scalar_one()
        tenant_id = str(tenant.id)

        hazard = (
            await session.execute(
                select(RiskHazard).where(
                    RiskHazard.tenant_id == tenant_id, RiskHazard.id == hazard_id
                )
            )
        ).scalar_one()
        assert hazard.title == "Работы на высоте"

        matrix_cells = (
            await session.execute(
                select(RiskMatrixCell).where(RiskMatrixCell.tenant_id == tenant_id)
            )
        ).scalars()
        assert len(list(matrix_cells)) == 9

        assessment = (
            await session.execute(
                select(RiskAssessment).where(
                    RiskAssessment.tenant_id == tenant_id,
                    RiskAssessment.id == assessment_id,
                )
            )
        ).scalar_one()
        assert assessment.score_after == 6
        assert assessment.controls == json.dumps(["harness"], ensure_ascii=False)
        assert assessment.created_by == "inspector-77"
        assert assessment.position_id == position_id
        assert assessment.place_id == site_id

        assessment_items = (
            await session.execute(
                select(RiskAssessmentItem).where(
                    RiskAssessmentItem.tenant_id == tenant_id,
                    RiskAssessmentItem.assessment_id == assessment_id,
                )
            )
        ).scalars().all()
        assert len(assessment_items) == 1
        assert assessment_items[0].score == 9

        risk_card = (
            await session.execute(
                select(RiskCard).where(
                    RiskCard.tenant_id == tenant_id,
                    RiskCard.assessment_id == assessment_id,
                )
            )
        ).scalar_one()
        assert risk_card.summary["items"][0]["hazard_code"] == "work_height"

        action_plan = (
            await session.execute(
                select(RiskActionPlan).where(
                    RiskActionPlan.tenant_id == tenant_id,
                    RiskActionPlan.assessment_id == assessment_id,
                )
            )
        ).scalar_one()
        plan_items = (
            await session.execute(
                select(RiskActionPlanItem).where(
                    RiskActionPlanItem.tenant_id == tenant_id,
                    RiskActionPlanItem.plan_id == action_plan.id,
                )
            )
        ).scalars().all()
        assert len(plan_items) == 1

        risk_map = (
            await session.execute(
                select(RiskMap).where(
                    RiskMap.tenant_id == tenant_id,
                    RiskMap.company_id == company_id,
                    RiskMap.site_id == site_id,
                    RiskMap.position_id == position_id,
                )
            )
        ).scalar_one()
        assert risk_map.matrix["total_assessments"] == 1

        outbox_entry = (
            await session.execute(
                select(Outbox).where(
                    Outbox.tenant_id == tenant_id,
                    Outbox.event_type == "RiskAssessed",
                )
            )
        ).scalar_one_or_none()
        assert outbox_entry is not None
        assert outbox_entry.payload["risk_assessment_id"] == assessment_id
