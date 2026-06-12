"""Честный контракт v1-роутера approval_signing после чистки симуляции (ЭДО Срез-1 / ed02).

Роутер смонтирован под /v1 внутри /api/v1 → базовый путь /api/v1/v1.

  * /sign:request, /sign/request: internal-fallback → ПЭП-ядро (signature_requests,
    signature_type="pep"); любой другой provider (вкл. бывший "stub") →
    409 SIGNATURE_PROVIDER_NOT_CONFIGURED, ничего не пишем.
  * /sign/submit: kind != "internal" (дефолт "un_ep") → 409; "internal" → ПЭП.
  * GET-читатели signature_requests: status — строка (после ed01 колонка VARCHAR;
    прежний r.status.value падал AttributeError → 500).
  * /edo:send, /edo/send: 409 EDO_PROVIDER_NOT_CONFIGURED, без записи.
  * Читатели edo_envelopes: после DROP (ed02) — честные {"items": []} / 404.
  * ЭДО-вебхуки: провайдер не сконфигурирован → 409.
"""
from __future__ import annotations

import pytest
from fastapi import status
from sqlalchemy import select

from app.models.models import RoleEnum, SignatureRequest

BASE = "/api/v1/v1"


async def _world(sessionmaker, data_factory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        _, version = await data_factory.create_document(tenant=tenant, session=session)
        await session.commit()
    return tenant, version


@pytest.mark.asyncio
async def test_sign_request_foreign_provider_409_and_writes_nothing(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    tenant, version = await _world(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN, tenant=tenant.slug)

    resp = await async_client.post(
        f"{BASE}/sign:request",
        json={"document_version_id": version.id, "provider": "stub"},
        headers=headers,
    )
    assert resp.status_code == status.HTTP_409_CONFLICT, resp.text
    assert resp.json()["detail"]["code"] == "SIGNATURE_PROVIDER_NOT_CONFIGURED"

    async with sessionmaker() as session:
        rows = (
            await session.execute(
                select(SignatureRequest).where(SignatureRequest.object_id == version.id)
            )
        ).scalars().all()
        assert rows == [], "409 не должен оставлять записей в signature_requests"


@pytest.mark.asyncio
async def test_sign_request_internal_fallback_goes_through_pep_core(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    tenant, version = await _world(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN, tenant=tenant.slug)

    resp = await async_client.post(
        f"{BASE}/sign:request",
        json={"document_version_id": version.id, "provider": "internal-fallback"},
        headers=headers,
    )
    assert resp.status_code == status.HTTP_200_OK, resp.text
    body = resp.json()
    # self-sign (signer == requested_by) → сразу signed; status — строка
    assert body["status"] == "signed"
    assert "signature_request_id" in body
    assert "provider_code" in body

    async with sessionmaker() as session:
        row = (
            await session.execute(
                select(SignatureRequest).where(SignatureRequest.id == body["signature_request_id"])
            )
        ).scalar_one()
        assert row.signature_type == "pep"
        assert row.provider == "internal"


@pytest.mark.asyncio
async def test_sign_request_alias_idempotency_replay(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    tenant, version = await _world(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN, tenant=tenant.slug)
    headers["Idempotency-Key"] = "v1-sign-request-honest-1"

    payload = {"document_version_id": version.id, "provider": "internal-fallback"}
    first = await async_client.post(f"{BASE}/sign/request", json=payload, headers=headers)
    second = await async_client.post(f"{BASE}/sign/request", json=payload, headers=headers)
    assert first.status_code == status.HTTP_200_OK, first.text
    assert second.status_code == status.HTTP_200_OK, second.text
    assert first.json()["signature_request_id"] == second.json()["signature_request_id"]


@pytest.mark.asyncio
async def test_sign_request_unknown_document_404(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    tenant, _ = await _world(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN, tenant=tenant.slug)

    resp = await async_client.post(
        f"{BASE}/sign:request",
        json={"document_version_id": "no-such-version", "provider": "internal-fallback"},
        headers=headers,
    )
    assert resp.status_code == status.HTTP_404_NOT_FOUND, resp.text


@pytest.mark.asyncio
async def test_sign_submit_default_kind_is_honest_409(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    tenant, version = await _world(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN, tenant=tenant.slug)

    resp = await async_client.post(
        f"{BASE}/sign/submit",
        json={"document_version_id": version.id, "signed_blob": "blob"},  # kind=un_ep по умолчанию
        headers=headers,
    )
    assert resp.status_code == status.HTTP_409_CONFLICT, resp.text
    assert resp.json()["detail"]["code"] == "SIGNATURE_PROVIDER_NOT_CONFIGURED"


@pytest.mark.asyncio
async def test_sign_submit_internal_then_readers_return_string_status(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    """Регресс 500-бага: после ed01 status в БД — VARCHAR, у строки нет .value."""
    tenant, version = await _world(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN, tenant=tenant.slug)

    submit = await async_client.post(
        f"{BASE}/sign/submit",
        json={"document_version_id": version.id, "kind": "internal", "signed_blob": "blob"},
        headers=headers,
    )
    assert submit.status_code == status.HTTP_200_OK, submit.text
    rid = submit.json()["id"]
    assert submit.json()["status"] == "signed"

    listing = await async_client.get(f"{BASE}/sign/requests", headers=headers)
    assert listing.status_code == status.HTTP_200_OK, listing.text
    items = listing.json()["items"]
    mine = next(item for item in items if item["id"] == rid)
    assert mine["status"] == "signed"
    assert isinstance(mine["status"], str)

    one = await async_client.get(f"{BASE}/sign/requests/{rid}", headers=headers)
    assert one.status_code == status.HTTP_200_OK, one.text
    assert one.json()["status"] == "signed"

    sign_status = await async_client.get(
        f"{BASE}/sign/status", params={"document_version_id": version.id}, headers=headers
    )
    assert sign_status.status_code == status.HTTP_200_OK, sign_status.text
    assert any(item["id"] == rid and item["status"] == "signed" for item in sign_status.json()["items"])


@pytest.mark.asyncio
async def test_edo_send_both_paths_409_provider_not_configured(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    tenant, version = await _world(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN, tenant=tenant.slug)

    for path in (f"{BASE}/edo:send", f"{BASE}/edo/send"):
        resp = await async_client.post(
            path,
            json={"document_version_id": version.id, "provider": "internal-fallback"},
            headers=headers,
        )
        assert resp.status_code == status.HTTP_409_CONFLICT, f"{path}: {resp.text}"
        assert resp.json()["detail"]["code"] == "EDO_PROVIDER_NOT_CONFIGURED"

    # после DROP edo_envelopes (ed02) читатели честно пустые
    envelopes = await async_client.get(f"{BASE}/edo/envelopes", headers=headers)
    assert envelopes.status_code == status.HTTP_200_OK
    assert envelopes.json() == {"items": []}

    messages = await async_client.get(f"{BASE}/edo/messages", headers=headers)
    assert messages.status_code == status.HTTP_200_OK
    assert messages.json() == {"items": []}

    one = await async_client.get(f"{BASE}/edo/envelopes/any-id", headers=headers)
    assert one.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_edo_webhooks_409_provider_not_configured(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    tenant, _ = await _world(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN, tenant=tenant.slug)

    by_provider = await async_client.post(
        f"{BASE}/edo/webhooks/mock",
        json={"external_id": "ext-1", "status": "delivered"},
        headers=headers,
    )
    assert by_provider.status_code == status.HTTP_409_CONFLICT, by_provider.text
    assert by_provider.json()["detail"]["code"] == "EDO_PROVIDER_NOT_CONFIGURED"

    by_status = await async_client.post(
        f"{BASE}/edo/webhook/status",
        json={"external_id": "ext-1", "status": "delivered"},
        headers=headers,
    )
    assert by_status.status_code == status.HTTP_409_CONFLICT, by_status.text
    assert by_status.json()["detail"]["code"] == "EDO_PROVIDER_NOT_CONFIGURED"
