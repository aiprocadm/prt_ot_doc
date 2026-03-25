from __future__ import annotations

import pytest
from fastapi import status


@pytest.mark.asyncio
async def test_edo_send_and_webhook_expose_non_production_provider_metadata(async_client, sessionmaker, make_auth_headers, data_factory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        tenant.settings = {"edo_webhook_secret": "dev-secret"}
        _, version = await data_factory.create_document(tenant=tenant, session=session)
        await session.commit()

    headers = await make_auth_headers()
    send = await async_client.post(
        "/api/v1/edo/send",
        json={"document_version_id": version.id, "provider_code": "mock"},
        headers=headers,
    )

    assert send.status_code == status.HTTP_200_OK
    assert send.json()["provider_mode"] == "non_production"
    assert send.json()["provider_production_ready"] is False

    hook = await async_client.post(
        "/api/v1/edo/webhooks/mock",
        json={"event_id": "evt-provider-meta", "external_id": send.json()["external_id"], "status": "accepted", "raw_payload": {}},
        headers=headers,
    )

    assert hook.status_code == status.HTTP_200_OK
    assert hook.json()["provider_code"] == "mock"
    assert hook.json()["provider_mode"] == "non_production"


@pytest.mark.asyncio
async def test_approval_sign_request_lists_provider_metadata(async_client, sessionmaker, make_auth_headers, data_factory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        _, version = await data_factory.create_document(tenant=tenant, session=session)
        await session.commit()

    headers = await make_auth_headers()
    create = await async_client.post(
        "/api/v1/sign/requests",
        json={
            "entity_type": "document",
            "entity_id": version.id,
            "signature_type": "internal",
            "provider_code": "mock",
        },
        headers=headers,
    )

    assert create.status_code == status.HTTP_200_OK
    assert create.json()["provider_mode"] == "non_production"

    listing = await async_client.get("/api/v1/sign/requests", headers=headers)
    assert listing.status_code == status.HTTP_200_OK
    assert listing.json()["items"][0]["provider_mode"] == "non_production"
