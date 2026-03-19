from __future__ import annotations

import pytest
from app.models.models import RoleEnum


@pytest.mark.anyio
async def test_machine_keys_and_public_api(async_client, sessionmaker, data_factory, make_auth_headers):
    async with sessionmaker() as session:  # type: AsyncSession
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(session=session, tenant=tenant)
        await data_factory.create_person(session=session, tenant=tenant, company=company, first_name="Ivan", last_name="Petrov")
        await data_factory.create_document(session=session, tenant=tenant, company=company)

    headers = await make_auth_headers(RoleEnum.ADMIN)
    created = await async_client.post("/api/v1/machine-keys", json={"name": "bot", "scopes": ["employees:read", "documents:read", "integrations:write"]}, headers={**headers, "X-Tenant": "test"})
    assert created.status_code == 201
    token = created.json()["token"]

    auth = await async_client.get("/api/v1/public/auth/machine", headers={"X-Tenant": "test", "X-API-Key": token})
    assert auth.status_code == 200

    people = await async_client.get("/api/v1/public/employees?limit=1&offset=0&sort_by=created_at&sort_order=asc", headers={"X-Tenant": "test", "X-API-Key": token})
    assert people.status_code == 200
    assert people.json()["total"] >= 1
    assert people.json()["limit"] == 1

    docs = await async_client.get("/api/v1/public/documents", headers={"X-Tenant": "test", "X-API-Key": token})
    assert docs.status_code == 200
    assert docs.json()["total"] >= 1

    webhook = await async_client.post(
        "/api/v1/public/integrations/webhooks/subscriptions",
        json={"name": "BI callback", "url": "https://example.test/public-hook", "subscribed_events": ["ExportDelivered"]},
        headers={"X-Tenant": "test", "X-API-Key": token},
    )
    assert webhook.status_code == 201
    assert webhook.json()["enabled"] is True

    rotated = await async_client.post(f"/api/v1/machine-keys/{created.json()['id']}/rotate", headers={**headers, "X-Tenant": "test"})
    assert rotated.status_code == 200
    new_token = rotated.json()["token"]

    old_auth = await async_client.get("/api/v1/public/auth/machine", headers={"X-Tenant": "test", "X-API-Key": token})
    assert old_auth.status_code == 401

    new_auth = await async_client.get("/api/v1/public/auth/machine", headers={"X-Tenant": "test", "X-API-Key": new_token})
    assert new_auth.status_code == 200
