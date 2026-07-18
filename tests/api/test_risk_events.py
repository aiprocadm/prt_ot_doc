from __future__ import annotations

import pytest
from fastapi import status
from sqlalchemy import select

from app.models.models import Outbox, OutboxStatus, RoleEnum, Site
from tests.utils.factories import TestDataFactory


@pytest.mark.asyncio
async def test_risk_assessment_emits_outbox(
    async_client, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    """Verify RiskAssessed event is emitted to outbox when risk assessment is created."""
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        site = Site(tenant_id=tenant.id, company_id=company.id, name="Test Site")
        session.add(site)
        await session.commit()
        await session.refresh(site)
        tenant_id = str(tenant.id)
        site_id = str(site.id)

    headers = await make_auth_headers(RoleEnum.ADMIN)

    # Create methodology
    methodology_resp = await async_client.post(
        "/api/v1/risk/methodologies",
        json={
            "name": "Test Matrix",
            "bands": [
                {"name": "low", "max": 4},
                {"name": "med", "max": 8},
                {"name": "high", "max": 25},
            ],
        },
        headers=headers,
    )
    assert methodology_resp.status_code == status.HTTP_200_OK
    methodology_id = methodology_resp.json()["id"]

    # Create hazard
    hazard_resp = await async_client.post(
        "/api/v1/risk/hazards",
        json={
            "code": "test-hazard",
            "title": "Test Hazard",
            "module": "ot",
            "recommended_measures": [{"text": "Take action", "due_in_days": 15}],
        },
        headers=headers,
    )
    assert hazard_resp.status_code == status.HTTP_200_OK

    # Create risk assessment
    assess_payload = {
        "company_id": company.id,
        "place_id": site_id,
        "methodology_id": methodology_id,
        "assessment_key": "test-assessment",
        "assessment_version": 1,
        "items": [
            {"hazard_code": "test-hazard", "probability": 2, "severity": 3},
        ],
    }
    assess_resp = await async_client.post(
        "/api/v1/risk/assess",
        json=assess_payload,
        headers=headers,
    )
    assert assess_resp.status_code == status.HTTP_200_OK
    assessment_id = assess_resp.json()["assessment_id"]

    # Verify RiskAssessed event in outbox
    async with sessionmaker() as session:
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
        assert outbox_entry.payload["hazard_code"] == "test-hazard"
        # Emitted = PENDING (awaiting dispatch) or SENT (no webhook destination
        # configured in the test -> the outbox marks it SENT immediately). Both
        # confirm the RiskAssessed event was emitted; status string is uppercase.
        assert outbox_entry.status in (OutboxStatus.PENDING, OutboxStatus.SENT)
