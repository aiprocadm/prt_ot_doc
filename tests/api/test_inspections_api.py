from __future__ import annotations

from datetime import date

import pytest
from fastapi import status
from sqlalchemy import select

from app.models.models import InspectionStatus, Outbox, RoleEnum
from tests.utils.factories import TestDataFactory


@pytest.mark.asyncio
async def test_inspection_flow(
    async_client, make_auth_headers, sessionmaker, data_factory: TestDataFactory
):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        site = await data_factory.create_site(tenant=tenant, company=company, session=session)
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN)
    payload = {
        "company_id": company.id,
        "site_id": site.id,
        "authority": "ГИТ",
        "purpose": "Плановая",
        "scheduled_at": date.today().isoformat(),
    }

    create_response = await async_client.post("/api/v1/inspections", json=payload, headers=headers)
    assert create_response.status_code == status.HTTP_201_CREATED, create_response.text
    inspection = create_response.json()
    assert inspection["authority"] == "ГИТ"

    list_response = await async_client.get(
        f"/api/v1/inspections?company_id={company.id}", headers=headers
    )
    assert list_response.status_code == status.HTTP_200_OK
    assert list_response.json()["total"] >= 1

    result_payload = {
        "title": "Акт проверки",
        "outcome": "предписание",
        "notes": "Выявлены нарушения",
        "issued_at": date.today().isoformat(),
    }
    result_response = await async_client.post(
        f"/api/v1/inspections/{inspection['id']}/results", json=result_payload, headers=headers
    )
    assert result_response.status_code == status.HTTP_201_CREATED, result_response.text
    result = result_response.json()
    assert result["title"] == "Акт проверки"

    update_payload = {
        "status": InspectionStatus.COMPLETED.value,
        "result_summary": "Предписание выдано",
    }
    update_response = await async_client.patch(
        f"/api/v1/inspections/{inspection['id']}", json=update_payload, headers=headers
    )
    assert update_response.status_code == status.HTTP_200_OK, update_response.text
    updated = update_response.json()
    assert updated["status"] == InspectionStatus.COMPLETED.value

    results_list = await async_client.get(
        f"/api/v1/inspections/{inspection['id']}/results", headers=headers
    )
    assert results_list.status_code == status.HTTP_200_OK
    assert len(results_list.json()) >= 1

    async with sessionmaker() as session:
        outbox = (
            (await session.execute(select(Outbox).where(Outbox.event_type == "InspectionCreated")))
            .scalars()
            .all()
        )
        assert any(item.payload.get("inspection_id") == inspection["id"] for item in outbox)
