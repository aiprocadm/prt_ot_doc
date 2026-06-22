from __future__ import annotations

import pytest
from fastapi import status


@pytest.mark.asyncio
async def test_edo_send_returns_409_provider_not_configured(
    async_client, sessionmaker, make_auth_headers, data_factory
):
    """Честный контракт: /edo/send без настроенного провайдера → 409 EDO_PROVIDER_NOT_CONFIGURED.

    Прежний тест проверял 200 + provider_mode (симуляция). После чистки симуляции
    эндпоинт сразу отказывает с корректным problem-detail.
    """
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

    assert send.status_code == status.HTTP_409_CONFLICT
    detail = send.json()["detail"]
    assert detail["code"] == "EDO_PROVIDER_NOT_CONFIGURED"


@pytest.mark.asyncio
async def test_sign_requests_non_pep_returns_409_provider_not_configured(
    async_client, sessionmaker, make_auth_headers, data_factory
):
    """Честный контракт: POST /sign/requests с signature_type != "pep" → 409 SIGNATURE_PROVIDER_NOT_CONFIGURED.

    Оркестратор принимает только ПЭП-тип; все внешние провайдеры подписи
    (KEP, UNEP, МЧД и любой неизвестный тип) не сконфигурированы.
    """
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

    assert create.status_code == status.HTTP_409_CONFLICT
    detail = create.json()["detail"]
    assert detail["code"] == "SIGNATURE_PROVIDER_NOT_CONFIGURED"
