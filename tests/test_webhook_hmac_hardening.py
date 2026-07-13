"""Fail-closed HMAC verification for every unauthenticated inbound webhook receiver.

These endpoints are reachable with only an ``X-Tenant`` header — either they are on the
``TenantMiddleware`` public allowlist (``/webhooks/inbound``, ``/edo/webhooks``,
``/edo/webhook/status``) or they carry no RBAC dependency (``/webhooks/edo``,
``/webhooks/sign``). The HMAC signature over the raw body is therefore the ONLY thing
authenticating the caller, so verification must fail CLOSED: with no configured secret an
endpoint cannot authenticate anyone and must reject every request rather than accept an
anonymous write.

Contract:
- no secret configured           -> 401 (fail closed)
- secret set, no signature header -> 401
- secret set, signature mismatch  -> 403
- secret set, correct signature   -> 2xx
"""

from __future__ import annotations

import hashlib
import hmac
import json

import pytest
from fastapi import status
from sqlalchemy import select

from app.core.config import reset_settings_cache
from app.models.models import Tenant
from app.models.workflow import SignatureRequest


def _sign(secret: str, raw: bytes) -> str:
    return hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()


async def _get_test_tenant(sessionmaker) -> Tenant:
    async with sessionmaker() as session:
        return (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()


async def _set_tenant_settings(sessionmaker, **settings: str) -> Tenant:
    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        tenant.settings = dict(settings)
        await session.commit()
        await session.refresh(tenant)
        return tenant


# --------------------------------------------------------------------------- #
# webhooks.py  —  POST /api/v1/webhooks/inbound/{source}  (global secret)      #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_inbound_rejects_when_no_secret_configured(
    async_client, sessionmaker, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With INBOUND_WEBHOOK_HMAC_SECRET unset the receiver must reject, not fail open."""
    monkeypatch.delenv("INBOUND_WEBHOOK_HMAC_SECRET", raising=False)
    reset_settings_cache()
    try:
        tenant = await _get_test_tenant(sessionmaker)
        monkeypatch.setattr(
            "app.api.routes.webhooks.process_inbound_webhook.delay", lambda **kwargs: None
        )
        response = await async_client.post(
            "/api/v1/webhooks/inbound/edo",
            json={"event_id": "evt-noconf", "external_id": "ext-1", "status": "accepted"},
            headers={"X-Tenant": tenant.slug},
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    finally:
        reset_settings_cache()


# --------------------------------------------------------------------------- #
# edo_workflow.py  —  POST /api/v1/edo/webhooks/{provider_code}  (tenant secret)#
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_edo_webhook_rejects_when_no_secret_configured(async_client, sessionmaker) -> None:
    """No per-tenant edo_webhook_secret -> reject anonymous write (fail closed)."""
    tenant = await _set_tenant_settings(sessionmaker)  # empty settings, no secret
    response = await async_client.post(
        "/api/v1/edo/webhooks/mock",
        json={"event_id": "evt-noconf", "external_id": "ext-1", "status": "accepted"},
        headers={"X-Tenant": tenant.slug},
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_edo_webhook_rejects_bad_signature(async_client, sessionmaker) -> None:
    tenant = await _set_tenant_settings(sessionmaker, edo_webhook_secret="dev-secret")
    body = {"event_id": "evt-bad", "external_id": "ext-1", "status": "accepted"}
    raw = json.dumps(body).encode("utf-8")
    response = await async_client.post(
        "/api/v1/edo/webhooks/mock",
        content=raw,
        headers={
            "X-Tenant": tenant.slug,
            "Content-Type": "application/json",
            "X-Signature": "deadbeef",
        },
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN


# --------------------------------------------------------------------------- #
# approval_orchestration.py  —  POST /api/v1/webhooks/edo/{operator_code}       #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_approval_edo_webhook_rejects_when_no_secret(async_client, sessionmaker) -> None:
    tenant = await _set_tenant_settings(sessionmaker)
    response = await async_client.post(
        "/api/v1/webhooks/edo/mock-operator",
        json={"status": "delivered"},
        headers={"X-Tenant": tenant.slug},
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_approval_edo_webhook_rejects_missing_signature(async_client, sessionmaker) -> None:
    tenant = await _set_tenant_settings(sessionmaker, edo_webhook_secret="dev-secret")
    response = await async_client.post(
        "/api/v1/webhooks/edo/mock-operator",
        json={"status": "delivered"},
        headers={"X-Tenant": tenant.slug},
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_approval_edo_webhook_rejects_bad_signature(async_client, sessionmaker) -> None:
    tenant = await _set_tenant_settings(sessionmaker, edo_webhook_secret="dev-secret")
    raw = json.dumps({"status": "delivered"}).encode("utf-8")
    response = await async_client.post(
        "/api/v1/webhooks/edo/mock-operator",
        content=raw,
        headers={
            "X-Tenant": tenant.slug,
            "Content-Type": "application/json",
            "X-Signature": "deadbeef",
        },
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_approval_edo_webhook_accepts_valid_signature(async_client, sessionmaker) -> None:
    tenant = await _set_tenant_settings(sessionmaker, edo_webhook_secret="dev-secret")
    raw = json.dumps({"status": "delivered"}).encode("utf-8")
    response = await async_client.post(
        "/api/v1/webhooks/edo/mock-operator",
        content=raw,
        headers={
            "X-Tenant": tenant.slug,
            "Content-Type": "application/json",
            "X-Signature": _sign("dev-secret", raw),
        },
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["status"] == "processed"


# --------------------------------------------------------------------------- #
# approval_orchestration.py  —  POST /api/v1/webhooks/sign/{provider_code}      #
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_approval_sign_webhook_rejects_when_no_secret(async_client, sessionmaker) -> None:
    tenant = await _set_tenant_settings(sessionmaker)
    response = await async_client.post(
        "/api/v1/webhooks/sign/mock-provider",
        json={"request_id": "does-not-matter", "status": "signed"},
        headers={"X-Tenant": tenant.slug},
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_approval_sign_webhook_rejects_bad_signature(async_client, sessionmaker) -> None:
    tenant = await _set_tenant_settings(sessionmaker, sign_webhook_secret="sign-secret")
    raw = json.dumps({"request_id": "does-not-matter", "status": "signed"}).encode("utf-8")
    response = await async_client.post(
        "/api/v1/webhooks/sign/mock-provider",
        content=raw,
        headers={
            "X-Tenant": tenant.slug,
            "Content-Type": "application/json",
            "X-Signature": "deadbeef",
        },
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_approval_sign_webhook_accepts_valid_signature(async_client, sessionmaker) -> None:
    tenant = await _set_tenant_settings(sessionmaker, sign_webhook_secret="sign-secret")
    async with sessionmaker() as session:
        sig_request = SignatureRequest(
            tenant_id=str(tenant.id),
            object_type="document_version",
            object_id="doc-1",
            provider="mock-provider",
            signature_type="kep",
        )
        session.add(sig_request)
        await session.commit()
        await session.refresh(sig_request)
        request_id = sig_request.id

    raw = json.dumps({"request_id": request_id, "status": "signed"}).encode("utf-8")
    response = await async_client.post(
        "/api/v1/webhooks/sign/mock-provider",
        content=raw,
        headers={
            "X-Tenant": tenant.slug,
            "Content-Type": "application/json",
            "X-Signature": _sign("sign-secret", raw),
        },
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["status"] == "signed"


# --------------------------------------------------------------------------- #
# edo_workflow.py  —  POST /api/v1/edo/webhook/status  (delegates to edo_webhook)#
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_edo_status_webhook_v1_rejects_when_no_secret(async_client, sessionmaker) -> None:
    tenant = await _set_tenant_settings(sessionmaker)
    response = await async_client.post(
        "/api/v1/edo/webhook/status",
        json={"event_id": "evt-1", "external_id": "ext-1", "status": "accepted"},
        headers={"X-Tenant": tenant.slug},
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_edo_status_webhook_v1_accepts_valid_signature(
    async_client, sessionmaker, monkeypatch: pytest.MonkeyPatch
) -> None:
    tenant = await _set_tenant_settings(sessionmaker, edo_webhook_secret="dev-secret")
    monkeypatch.setattr(
        "app.api.routes.edo_workflow.process_inbound_webhook.delay", lambda **kwargs: None
    )
    raw = json.dumps({"event_id": "evt-2", "external_id": "ext-2", "status": "accepted"}).encode(
        "utf-8"
    )
    response = await async_client.post(
        "/api/v1/edo/webhook/status",
        content=raw,
        headers={
            "X-Tenant": tenant.slug,
            "Content-Type": "application/json",
            "X-Signature": _sign("dev-secret", raw),
        },
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["status"] == "accepted"
