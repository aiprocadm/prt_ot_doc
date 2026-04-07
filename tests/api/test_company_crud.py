from __future__ import annotations

import pytest
from fastapi import status

from app.models.models import RoleEnum
from tests.utils.factories import TestDataFactory


@pytest.mark.asyncio
async def test_company_crud_lifecycle(async_client, make_auth_headers):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    payload = {
        "name": "Acme Holdings",
        "legal_address": "HQ",
        "actual_address": "HQ",
        "phone_numbers": ["+7 495 000-00-01"],
    }

    create_response = await async_client.post(
        "/api/v1/companies", json=payload, headers=headers
    )
    assert create_response.status_code == status.HTTP_201_CREATED
    company = create_response.json()

    read_response = await async_client.get(
        f"/api/v1/companies/{company['id']}", headers=headers
    )
    assert read_response.status_code == status.HTTP_200_OK
    assert read_response.json()["name"] == payload["name"]

    update_response = await async_client.patch(
        f"/api/v1/companies/{company['id']}",
        json={"name": "Acme Updated", "phone_numbers": ["+1 555 0101"]},
        headers=headers,
    )
    assert update_response.status_code == status.HTTP_200_OK
    assert update_response.json()["name"] == "Acme Updated"

    list_response = await async_client.get("/api/v1/companies", headers=headers)
    assert list_response.status_code == status.HTTP_200_OK
    assert list_response.json()["total"] >= 1

    delete_response = await async_client.delete(
        f"/api/v1/companies/{company['id']}", headers=headers
    )
    assert delete_response.status_code == status.HTTP_204_NO_CONTENT

    final_list = await async_client.get("/api/v1/companies", headers=headers)
    assert final_list.json()["total"] == 0


@pytest.mark.asyncio
async def test_company_isolation_between_tenants(
    async_client, make_auth_headers, sessionmaker, data_factory: TestDataFactory
):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(slug="acme", session=session)
        company = await data_factory.create_company(
            tenant=tenant, name="Foreign Co", session=session
        )
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN)
    response = await async_client.get(
        f"/api/v1/companies/{company.id}", headers=headers
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_company_update_delete_denied_across_tenants(
    async_client, make_auth_headers, sessionmaker, data_factory: TestDataFactory
):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(slug="acme", session=session)
        company = await data_factory.create_company(
            tenant=tenant, name="Foreign Co 2", session=session
        )
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN)

    update_response = await async_client.patch(
        f"/api/v1/companies/{company.id}",
        json={"name": "Should Not Update"},
        headers=headers,
    )
    assert update_response.status_code == status.HTTP_404_NOT_FOUND

    delete_response = await async_client.delete(
        f"/api/v1/companies/{company.id}",
        headers=headers,
    )
    assert delete_response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_company_error_payload_contains_correlation_headers(
    async_client, make_auth_headers, sessionmaker, data_factory: TestDataFactory
):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(slug="acme", session=session)
        company = await data_factory.create_company(
            tenant=tenant, name="Foreign Co 3", session=session
        )
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN)
    headers["X-Correlation-Id"] = "company-crud-corr-id"
    response = await async_client.get(f"/api/v1/companies/{company.id}", headers=headers)

    assert response.status_code == status.HTTP_404_NOT_FOUND
    body = response.json()
    assert body["correlation_id"] == "company-crud-corr-id"
    assert "company-crud-corr-id" in response.headers["X-Correlation-Id"]
