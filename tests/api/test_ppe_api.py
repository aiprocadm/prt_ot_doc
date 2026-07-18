from __future__ import annotations

import pytest
from fastapi import status

from app.models.models import RoleEnum
from tests.utils.factories import TestDataFactory


@pytest.mark.asyncio
async def test_ppe_api_flow(
    async_client, make_auth_headers, sessionmaker, data_factory: TestDataFactory
):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        person = await data_factory.create_person(tenant=tenant, company=company, session=session)
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN)

    item_payload = {
        "name": "Каска",
        "code": "helmet",
        "category": "head",
        "default_wear_days": 180,
        "metadata_json": {"color": "orange"},
    }
    item_response = await async_client.post("/api/v1/ppe/items", json=item_payload, headers=headers)
    assert item_response.status_code == status.HTTP_201_CREATED
    item = item_response.json()

    list_response = await async_client.get("/api/v1/ppe/items", headers=headers)
    assert list_response.status_code == status.HTTP_200_OK
    assert list_response.json()["total"] >= 1

    issue_payload = {
        "person_id": person.id,
        "item_id": item["id"],
        "quantity": 2,
        "wear_days": 30,
    }
    issue_response = await async_client.post(
        "/api/v1/ppe/issues", json=issue_payload, headers=headers
    )
    assert issue_response.status_code == status.HTTP_201_CREATED
    issue = issue_response.json()
    assert issue["quantity"] == 2
    assert issue["item_name"] == "Каска"

    expiring_response = await async_client.get(
        "/api/v1/ppe/issues/expiring?within_days=60", headers=headers
    )
    assert expiring_response.status_code == status.HTTP_200_OK
    assert expiring_response.json()["total"] >= 1

    update_response = await async_client.patch(
        f"/api/v1/ppe/issues/{issue['id']}",
        json={"status": "returned"},
        headers=headers,
    )
    assert update_response.status_code == status.HTTP_200_OK
    assert update_response.json()["status"] == "returned"
