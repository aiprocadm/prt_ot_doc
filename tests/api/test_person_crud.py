from __future__ import annotations

import pytest
from fastapi import status

from app.models.models import RoleEnum
from tests.utils.factories import TestDataFactory


@pytest.mark.asyncio
async def test_person_crud_flow(
    async_client, make_auth_headers, sessionmaker, data_factory: TestDataFactory
):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN)
    payload = {
        "company_id": company.id,
        "first_name": "John",
        "last_name": "Smith",
        "personnel_number": "123",
    }

    create_response = await async_client.post("/api/v1/persons", json=payload, headers=headers)
    assert create_response.status_code == status.HTTP_201_CREATED
    person = create_response.json()
    assert person["company_id"] == company.id

    get_response = await async_client.get(f"/api/v1/persons/{person['id']}", headers=headers)
    assert get_response.status_code == status.HTTP_200_OK

    patch_response = await async_client.patch(
        f"/api/v1/persons/{person['id']}",
        json={"first_name": "Johnny", "personnel_number": "999"},
        headers=headers,
    )
    assert patch_response.status_code == status.HTTP_200_OK
    assert patch_response.json()["first_name"] == "Johnny"

    list_response = await async_client.get("/api/v1/persons", headers=headers)
    assert list_response.status_code == status.HTTP_200_OK
    assert list_response.json()["total"] == 1

    delete_response = await async_client.delete(f"/api/v1/persons/{person['id']}", headers=headers)
    assert delete_response.status_code == status.HTTP_204_NO_CONTENT

    final_list = await async_client.get("/api/v1/persons", headers=headers)
    assert final_list.json()["total"] == 0
