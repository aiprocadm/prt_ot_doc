from __future__ import annotations

from datetime import date

import pytest
from fastapi import status

from app.models.models import RoleEnum
from tests.utils.factories import TestDataFactory


@pytest.mark.asyncio
async def test_journal_api_flow(
    async_client, make_auth_headers, sessionmaker, data_factory: TestDataFactory
):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        person = await data_factory.create_person(tenant=tenant, company=company, session=session)
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN)

    journal_payload = {
        "company_id": company.id,
        "title": "Журнал вводного инструктажа",
        "journal_type": "introductory",
        "started_at": str(date.today()),
    }
    journal_response = await async_client.post(
        "/api/v1/journals", json=journal_payload, headers=headers
    )
    assert journal_response.status_code == status.HTTP_201_CREATED
    journal = journal_response.json()

    entry_payload = {
        "person_id": person.id,
        "entry_type": "introductory",
        "entry_date": str(date.today()),
        "instructor": "Иванов И.И.",
        "notes": "Проведен вводный инструктаж",
    }
    entry_response = await async_client.post(
        f"/api/v1/journals/{journal['id']}/entries", json=entry_payload, headers=headers
    )
    assert entry_response.status_code == status.HTTP_201_CREATED
    entry = entry_response.json()

    list_response = await async_client.get(
        f"/api/v1/journals/{journal['id']}/entries", headers=headers
    )
    assert list_response.status_code == status.HTTP_200_OK
    assert list_response.json()["total"] == 1

    update_response = await async_client.patch(
        f"/api/v1/journals/entries/{entry['id']}",
        json={"notes": "Отметка о проверке знаний"},
        headers=headers,
    )
    assert update_response.status_code == status.HTTP_200_OK
    assert update_response.json()["notes"] == "Отметка о проверке знаний"

    export_response = await async_client.get(
        f"/api/v1/journals/{journal['id']}/export", headers=headers
    )
    assert export_response.status_code == status.HTTP_200_OK
    payload = export_response.json()
    assert payload["journal"]["id"] == journal["id"]
    assert len(payload["entries"]) == 1
