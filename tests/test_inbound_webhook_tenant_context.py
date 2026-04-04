from __future__ import annotations

import hashlib
import hmac
import json

import pytest
from fastapi import status
from sqlalchemy import select

from app.core.config import reset_settings_cache
from app.models.models import Tenant


@pytest.mark.asyncio
async def test_webhooks_inbound_passes_tenant_slug_to_worker(
    async_client,
    sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()

    captured: dict[str, object] = {}

    def _fake_delay(*, source: str, tenant_slug: str, payload: dict[str, object]) -> None:
        captured.update(source=source, tenant_slug=tenant_slug, payload=payload)

    monkeypatch.setattr("app.api.routes.webhooks.process_inbound_webhook.delay", _fake_delay)

    response = await async_client.post(
        "/api/v1/webhooks/inbound/edo",
        json={"event_id": "evt-tenant-slug", "external_id": "ext-1", "status": "accepted"},
        headers={"X-Tenant": tenant.slug},
    )

    assert response.status_code == status.HTTP_202_ACCEPTED
    assert response.json()["status"] == "accepted"
    assert captured["source"] == "edo"
    assert captured["tenant_slug"] == tenant.slug


@pytest.mark.asyncio
async def test_edo_webhook_passes_tenant_slug_to_worker(
    async_client,
    sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        tenant.settings = {"edo_webhook_secret": "dev-secret"}
        await session.commit()

    captured: dict[str, object] = {}

    def _fake_delay(*, source: str, tenant_slug: str, payload: dict[str, object]) -> None:
        captured.update(source=source, tenant_slug=tenant_slug, payload=payload)

    monkeypatch.setattr("app.api.routes.edo_workflow.process_inbound_webhook.delay", _fake_delay)

    response = await async_client.post(
        "/api/v1/edo/webhooks/mock",
        json={"event_id": "evt-edo-tenant", "external_id": "ext-2", "status": "accepted", "raw_payload": {"k": "v"}},
        headers={"X-Tenant": tenant.slug},
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["status"] == "accepted"
    assert captured["source"] == "edo"
    assert captured["tenant_slug"] == tenant.slug


@pytest.mark.asyncio
async def test_inbound_requires_hmac_when_secret_configured(
    async_client,
    sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("INBOUND_WEBHOOK_HMAC_SECRET", "integration-test-hmac")
    reset_settings_cache()
    try:
        async with sessionmaker() as session:
            tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()

        monkeypatch.setattr("app.api.routes.webhooks.process_inbound_webhook.delay", lambda **kwargs: None)

        body = {"event_id": "evt-hmac", "external_id": "ext-hmac", "status": "accepted"}
        raw = json.dumps(body).encode("utf-8")
        sig = hmac.new(b"integration-test-hmac", raw, hashlib.sha256).hexdigest()

        missing_sig = await async_client.post(
            "/api/v1/webhooks/inbound/edo",
            content=raw,
            headers={"X-Tenant": tenant.slug, "Content-Type": "application/json"},
        )
        assert missing_sig.status_code == status.HTTP_401_UNAUTHORIZED

        ok = await async_client.post(
            "/api/v1/webhooks/inbound/edo",
            content=raw,
            headers={
                "X-Tenant": tenant.slug,
                "Content-Type": "application/json",
                "X-Inbound-Webhook-Signature": sig,
            },
        )
        assert ok.status_code == status.HTTP_202_ACCEPTED
    finally:
        monkeypatch.delenv("INBOUND_WEBHOOK_HMAC_SECRET", raising=False)
        reset_settings_cache()


@pytest.mark.asyncio
async def test_inbound_rejects_invalid_json(
    async_client,
    sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()

    monkeypatch.setattr("app.api.routes.webhooks.process_inbound_webhook.delay", lambda **kwargs: None)

    response = await async_client.post(
        "/api/v1/webhooks/inbound/edo",
        content=b"not-json",
        headers={"X-Tenant": tenant.slug, "Content-Type": "application/json"},
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json().get("code") == "INVALID_JSON"
