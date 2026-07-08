from __future__ import annotations

from datetime import datetime, timedelta, timezone

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
async def test_closed_incident_cannot_be_reopened(
    async_client, make_auth_headers, sessionmaker, data_factory: TestDataFactory
):
    """A CLOSED/CANCELLED incident is terminal: a generic PATCH must not reopen it."""
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        site = await data_factory.create_site(tenant=tenant, company=company, session=session)
        victim = await data_factory.create_person(tenant=tenant, company=company, session=session)
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN)
    payload = {
        "title": "Инцидент",
        "incident_type": IncidentType.ACCIDENT.value,
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "company_id": company.id,
        "site_id": site.id,
        "severity": IncidentSeverity.HIGH.value,
        "description": "desc",
        "victim_ids": [victim.id],
    }
    created = (
        await async_client.post("/api/v1/incidents", json=payload, headers=headers)
    ).json()

    close = await async_client.patch(
        f"/api/v1/incidents/{created['id']}",
        json={"status": IncidentStatus.CLOSED.value},
        headers=headers,
    )
    assert close.status_code == status.HTTP_200_OK, close.text

    reopen = await async_client.patch(
        f"/api/v1/incidents/{created['id']}",
        json={"status": IncidentStatus.INVESTIGATING.value},
        headers=headers,
    )
    assert reopen.status_code == status.HTTP_400_BAD_REQUEST, reopen.text


@pytest.mark.asyncio
async def test_incident_flow(
    async_client, make_auth_headers, sessionmaker, data_factory: TestDataFactory
):
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

    list_response = await async_client.get(
        f"/api/v1/incidents?company_id={company.id}", headers=headers
    )
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
        outbox = (
            (await session.execute(select(Outbox).where(Outbox.event_type == "IncidentCreated")))
            .scalars()
            .all()
        )
        assert any(item.payload.get("incident_id") == created["id"] for item in outbox)


@pytest.mark.skip(
    reason="/api/v1/incidents/{id}/capa convenience endpoint is not implemented; "
    "CAPA is modeled via /corrective-actions (source_type=incident, source_id)."
)
@pytest.mark.asyncio
async def test_incident_capa_deadline_enforcement(
    async_client, make_auth_headers, sessionmaker, data_factory: TestDataFactory
):
    """Verify CAPA action items have deadline enforcement."""
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        site = await data_factory.create_site(tenant=tenant, company=company, session=session)
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN)

    # Create incident
    incident_payload = {
        "title": "Deadline Test Incident",
        "incident_type": IncidentType.ACCIDENT.value,
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "company_id": company.id,
        "site_id": site.id,
        "severity": IncidentSeverity.MEDIUM.value,
        "description": "Test for CAPA deadlines",
        "location_description": "Test Site",
    }
    incident_resp = await async_client.post(
        "/api/v1/incidents", json=incident_payload, headers=headers
    )
    assert incident_resp.status_code == status.HTTP_201_CREATED
    incident_id = incident_resp.json()["id"]

    # Add CAPA action with deadline (30 days from now)
    due_date = (datetime.now(timezone.utc) + timedelta(days=30)).date().isoformat()
    capa_payload = {
        "action_text": "Implement safety barrier",
        "responsible_person_id": None,
        "due_date": due_date,
        "status": "open",
    }
    capa_resp = await async_client.post(
        f"/api/v1/incidents/{incident_id}/capa", json=capa_payload, headers=headers
    )
    # Verify response is successful (201 or 200 depending on implementation)
    assert capa_resp.status_code in (status.HTTP_201_CREATED, status.HTTP_200_OK), capa_resp.text

    # List incident CAPA items
    capa_list_resp = await async_client.get(
        f"/api/v1/incidents/{incident_id}/capa", headers=headers
    )
    assert capa_list_resp.status_code == status.HTTP_200_OK
    capa_items = capa_list_resp.json()
    if isinstance(capa_items, dict):
        capa_items = capa_items.get("items", [])
    assert len(capa_items) >= 1
    # Verify deadline is set
    assert any(item.get("due_date") == due_date for item in capa_items)
