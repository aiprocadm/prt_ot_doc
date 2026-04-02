from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import status
from sqlalchemy import select

from app.models.models import (
    IncidentSeverity,
    IncidentStage,
    IncidentStatus,
    IncidentType,
    Outbox,
    RoleEnum,
)
from tests.utils.factories import TestDataFactory


@pytest.mark.asyncio
async def test_incident_flow(async_client, make_auth_headers, sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        site = await data_factory.create_site(tenant=tenant, company=company, session=session)
        victim = await data_factory.create_person(tenant=tenant, company=company, session=session)
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN)
    payload = {
        "title": "Падение груза",
        "incident_type": IncidentType.ACCIDENT.value,
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "company_id": company.id,
        "site_id": site.id,
        "severity": IncidentSeverity.HIGH.value,
        "description": "Рабочий получил травму при падении груза",
        "location_description": "Склад №1",
        "victim_ids": [victim.id],
    }

    create_response = await async_client.post("/api/v1/incidents", json=payload, headers=headers)
    assert create_response.status_code == status.HTTP_201_CREATED, create_response.text
    created = create_response.json()
    assert created["incident_type"] == IncidentType.ACCIDENT.value
    assert victim.id in created["victim_ids"]

    list_response = await async_client.get(f"/api/v1/incidents?company_id={company.id}", headers=headers)
    assert list_response.status_code == status.HTTP_200_OK
    assert list_response.json()["total"] >= 1

    log_payload = {
        "stage": IncidentStage.INVESTIGATION.value,
        "status": IncidentStatus.INVESTIGATING.value,
        "message": "Назначена комиссия, собраны объяснения",
        "metadata_json": {"chair": "Иванов"},
    }
    log_response = await async_client.post(
        f"/api/v1/incidents/{created['id']}/logs", json=log_payload, headers=headers
    )
    assert log_response.status_code == status.HTTP_201_CREATED, log_response.text
    log_entry = log_response.json()
    assert log_entry["stage"] == IncidentStage.INVESTIGATION.value

    update_payload = {
        "status": IncidentStatus.CLOSED.value,
        "investigation_stage": IncidentStage.CLOSED.value,
        "victim_ids": [victim.id],
    }
    update_response = await async_client.patch(
        f"/api/v1/incidents/{created['id']}", json=update_payload, headers=headers
    )
    assert update_response.status_code == status.HTTP_200_OK, update_response.text
    updated = update_response.json()
    assert updated["status"] == IncidentStatus.CLOSED.value

    logs_list = await async_client.get(f"/api/v1/incidents/{created['id']}/logs", headers=headers)
    assert logs_list.status_code == status.HTTP_200_OK
    assert len(logs_list.json()) >= 1

    async with sessionmaker() as session:
        outbox = (await session.execute(select(Outbox).where(Outbox.event_type == "IncidentCreated"))).scalars().all()
        assert any(item.payload.get("incident_id") == created["id"] for item in outbox)
