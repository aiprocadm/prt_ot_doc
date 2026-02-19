from __future__ import annotations

import pytest
from fastapi import status
from sqlalchemy import select

from app.models.models import ApprovalRequest, EdoMessage, Outbox, Signature


@pytest.mark.asyncio
async def test_idempotency_key_same_request_returns_same_response(async_client, sessionmaker, make_auth_headers, data_factory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        _, version = await data_factory.create_document(tenant=tenant, session=session)
    headers = await make_auth_headers()
    headers["Idempotency-Key"] = "approval-start-1"
    await async_client.post(
        "/api/v1/approvals/routes",
        json={"code": "DOC_ROUTE", "name": "Doc route", "rules_json": {"steps": [{"order": 1, "role": "admin"}]}, "version": 1},
        headers=headers,
    )
    first = await async_client.post(
        "/api/v1/approvals/requests",
        json={"document_version_id": version.id, "route_code": "DOC_ROUTE"},
        headers=headers,
    )
    second = await async_client.post(
        "/api/v1/approvals/requests",
        json={"document_version_id": version.id, "route_code": "DOC_ROUTE"},
        headers=headers,
    )
    assert first.status_code == status.HTTP_200_OK
    assert second.status_code == status.HTTP_200_OK
    assert first.json()["id"] == second.json()["id"]


@pytest.mark.asyncio
async def test_idempotency_key_different_body_returns_409(async_client, sessionmaker, make_auth_headers, data_factory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        _, v1 = await data_factory.create_document(tenant=tenant, session=session)
    headers = await make_auth_headers()
    headers["Idempotency-Key"] = "edo-send-1"
    first = await async_client.post("/api/v1/edo/send", json={"document_version_id": v1.id, "provider_code": "mock"}, headers=headers)
    second = await async_client.post("/api/v1/edo/send", json={"document_version_id": v1.id, "provider_code": "other"}, headers=headers)
    assert first.status_code == status.HTTP_200_OK
    assert second.status_code == status.HTTP_409_CONFLICT


@pytest.mark.asyncio
async def test_approval_signature_and_edo_webhook_flow(async_client, sessionmaker, make_auth_headers, data_factory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        tenant.settings = {"edo_webhook_secret": "dev-secret"}
        _, version = await data_factory.create_document(tenant=tenant, session=session)
        await session.commit()
    headers = await make_auth_headers()

    route = await async_client.post(
        "/api/v1/approvals/routes",
        json={"code": "FLOW_ROUTE", "name": "Flow route", "rules_json": {"steps": [{"order": 1, "role": "admin"}]}, "version": 1},
        headers=headers,
    )
    assert route.status_code == status.HTTP_200_OK

    start = await async_client.post(
        "/api/v1/approvals/requests",
        json={"document_version_id": version.id, "route_code": "FLOW_ROUTE"},
        headers=headers,
    )
    assert start.status_code == status.HTTP_200_OK
    request_id = start.json()["id"]

    decide = await async_client.post(
        f"/api/v1/approvals/requests/{request_id}/decide",
        json={"decision": "approve"},
        headers=headers,
    )
    assert decide.status_code == status.HTTP_200_OK
    assert decide.json()["status"] == "approved"

    sign = await async_client.post(
        "/api/v1/signatures",
        json={"document_version_id": version.id, "type": "INTERNAL"},
        headers=headers,
    )
    assert sign.status_code == status.HTTP_200_OK

    send = await async_client.post(
        "/api/v1/edo/send",
        json={"document_version_id": version.id, "provider_code": "mock"},
        headers=headers,
    )
    assert send.status_code == status.HTTP_200_OK
    external_id = send.json()["external_id"]

    webhook_payload = {"event_id": "evt-1", "external_id": external_id, "status": "accepted", "raw_payload": {"provider": "mock"}}
    hook = await async_client.post(
        "/api/v1/edo/webhooks/mock",
        json=webhook_payload,
        headers=headers,
    )
    assert hook.status_code == status.HTTP_200_OK

    async with sessionmaker() as session:
        assert (await session.execute(select(ApprovalRequest))).scalar_one_or_none() is not None
        assert (await session.execute(select(Signature))).scalar_one_or_none() is not None
        message = (await session.execute(select(EdoMessage))).scalar_one_or_none()
        assert message is not None
        assert message.status.value == "accepted"
        outbox_signed = (
            await session.execute(select(Outbox).where(Outbox.event_type == "DocumentSigned"))
        ).scalars().all()
        assert outbox_signed
