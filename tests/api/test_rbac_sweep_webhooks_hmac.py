"""HMAC verification for approval_orchestration inbound webhooks (Tier-1w).

The RBAC route-group audit (docs/audit/RBAC_ROUTE_GROUP_AUDIT_2026-07-12.md)
flagged ``POST /webhooks/edo/{operator_code}`` and ``POST /webhooks/sign/{provider_code}``
as reachable with only a tenant-slug header and NO payload authentication — an
external caller who knows the tenant slug + a request_id could flip EDO / signing
state. These are machine-called endpoints, so the correct control is an HMAC
signature over the raw body (not a user role). We reuse the house helper
``verify_inbound_webhook_body_hmac`` (same as webhooks.py /inbound/{source}): when
``INBOUND_WEBHOOK_HMAC_SECRET`` is configured, a valid ``X-Inbound-Webhook-Signature``
is required; a missing/invalid signature is rejected.
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

_SECRET = "approval-webhook-hmac-secret"


def _sign(raw: bytes) -> str:
    return hmac.new(_SECRET.encode("utf-8"), raw, hashlib.sha256).hexdigest()


@pytest.mark.anyio
async def test_edo_webhook_requires_hmac_when_secret_configured(
    async_client, sessionmaker, monkeypatch
) -> None:
    monkeypatch.setenv("INBOUND_WEBHOOK_HMAC_SECRET", _SECRET)
    reset_settings_cache()
    try:
        async with sessionmaker() as session:
            tenant = (
                await session.execute(select(Tenant).where(Tenant.slug == "test"))
            ).scalar_one()

        raw = json.dumps({"external_event_id": "evt-hmac-edo"}).encode("utf-8")
        base_headers = {"X-Tenant": tenant.slug, "Content-Type": "application/json"}

        missing = await async_client.post(
            "/api/v1/webhooks/edo/testop", content=raw, headers=base_headers
        )
        assert missing.status_code == status.HTTP_401_UNAUTHORIZED

        ok = await async_client.post(
            "/api/v1/webhooks/edo/testop",
            content=raw,
            headers={**base_headers, "X-Inbound-Webhook-Signature": _sign(raw)},
        )
        assert ok.status_code == status.HTTP_200_OK
    finally:
        monkeypatch.delenv("INBOUND_WEBHOOK_HMAC_SECRET", raising=False)
        reset_settings_cache()


@pytest.mark.anyio
async def test_sign_webhook_requires_hmac_when_secret_configured(
    async_client, sessionmaker, monkeypatch
) -> None:
    monkeypatch.setenv("INBOUND_WEBHOOK_HMAC_SECRET", _SECRET)
    reset_settings_cache()
    try:
        async with sessionmaker() as session:
            tenant = (
                await session.execute(select(Tenant).where(Tenant.slug == "test"))
            ).scalar_one()

        raw = json.dumps({"request_id": "nonexistent-request"}).encode("utf-8")
        base_headers = {"X-Tenant": tenant.slug, "Content-Type": "application/json"}

        missing = await async_client.post(
            "/api/v1/webhooks/sign/prov", content=raw, headers=base_headers
        )
        assert missing.status_code == status.HTTP_401_UNAUTHORIZED

        signed = await async_client.post(
            "/api/v1/webhooks/sign/prov",
            content=raw,
            headers={**base_headers, "X-Inbound-Webhook-Signature": _sign(raw)},
        )
        # HMAC clears; the unknown request_id then yields 404 (not 401).
        assert signed.status_code != status.HTTP_401_UNAUTHORIZED
        assert signed.status_code == status.HTTP_404_NOT_FOUND
    finally:
        monkeypatch.delenv("INBOUND_WEBHOOK_HMAC_SECRET", raising=False)
        reset_settings_cache()
