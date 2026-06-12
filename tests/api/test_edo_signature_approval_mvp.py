from __future__ import annotations

import pytest
from fastapi import status
from sqlalchemy import select

from app.models.models import ApprovalRequest, SignatureRequest


@pytest.mark.asyncio
async def test_idempotency_key_same_request_returns_same_response(async_client, sessionmaker, make_auth_headers, data_factory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        _, version = await data_factory.create_document(tenant=tenant, session=session)
    headers = await make_auth_headers()
    headers["Idempotency-Key"] = "route-create-1"
    await async_client.post(
        "/api/v1/approvals/routes",
        json={"code": "DOC_ROUTE", "name": "Doc route", "rules_json": {"steps": [{"order": 1, "role": "admin"}]}, "version": 1},
        headers=headers,
    )
    headers["Idempotency-Key"] = "approval-start-1"
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
async def test_edo_send_honest_409_provider_not_configured(async_client, sessionmaker, make_auth_headers, data_factory):
    """Честный контракт: /edo/send всегда 409 EDO_PROVIDER_NOT_CONFIGURED.

    Идемпотентная запись не сохраняется при 409-ответе, поэтому повторный
    запрос с тем же ключом и ДРУГИМ телом тоже возвращает
    409 EDO_PROVIDER_NOT_CONFIGURED — а не 409 IDEMPOTENCY_MISMATCH.
    """
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        _, v1 = await data_factory.create_document(tenant=tenant, session=session)
    headers = await make_auth_headers()
    headers["Idempotency-Key"] = "edo-send-honest-1"

    first = await async_client.post(
        "/api/v1/edo/send",
        json={"document_version_id": v1.id, "provider_code": "mock"},
        headers=headers,
    )
    assert first.status_code == status.HTTP_409_CONFLICT
    assert first.json()["detail"]["code"] == "EDO_PROVIDER_NOT_CONFIGURED"

    # Второй запрос — тот же ключ, другое тело.
    # Запись не была сохранена (провайдер не настроен → raise до flush),
    # поэтому снова получаем EDO_PROVIDER_NOT_CONFIGURED, а не IDEMPOTENCY_MISMATCH.
    second = await async_client.post(
        "/api/v1/edo/send",
        json={"document_version_id": v1.id, "provider_code": "other"},
        headers=headers,
    )
    assert second.status_code == status.HTTP_409_CONFLICT
    assert second.json()["detail"]["code"] == "EDO_PROVIDER_NOT_CONFIGURED"


@pytest.mark.asyncio
async def test_approval_then_pep_signature_then_edo_send_409(async_client, sessionmaker, make_auth_headers, data_factory):
    """Честный флоу согласования + подпись через ПЭП-ядро + 409 на /edo/send.

    Шаги:
    1. Создать маршрут согласования.
    2. Запустить согласование, принять решение → статус «approved».
    3. POST /signatures type=INTERNAL → ПЭП-запись, status=«signed» (self-sign).
    4. GET /sign/pep/requests?object_type=document_version&object_id=... → запись найдена.
    5. POST /edo/send → 409 EDO_PROVIDER_NOT_CONFIGURED.
    """
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

    # INTERNAL-подпись через ПЭП-ядро — self-sign (signer=requester), сразу signed.
    sign = await async_client.post(
        "/api/v1/signatures",
        json={"document_version_id": version.id, "type": "INTERNAL"},
        headers=headers,
    )
    assert sign.status_code == status.HTTP_200_OK
    sign_body = sign.json()
    assert sign_body["status"] == "signed"

    # ПЭП-журнал содержит запись для этого документа.
    pep_list = await async_client.get(
        "/api/v1/sign/pep/requests",
        params={"object_type": "document_version", "object_id": version.id},
        headers=headers,
    )
    assert pep_list.status_code == status.HTTP_200_OK
    pep_items = pep_list.json()["items"]
    assert any(item["id"] == sign_body["id"] for item in pep_items)

    # ЭДО-провайдер не настроен — честный 409.
    send = await async_client.post(
        "/api/v1/edo/send",
        json={"document_version_id": version.id, "provider_code": "mock"},
        headers=headers,
    )
    assert send.status_code == status.HTTP_409_CONFLICT
    assert send.json()["detail"]["code"] == "EDO_PROVIDER_NOT_CONFIGURED"

    async with sessionmaker() as session:
        assert (await session.execute(select(ApprovalRequest))).scalar_one_or_none() is not None
        assert (await session.execute(select(SignatureRequest))).scalar_one_or_none() is not None
