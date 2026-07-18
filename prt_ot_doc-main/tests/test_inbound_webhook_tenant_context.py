from __future__ import annotations

import pytest
from fastapi import status
from sqlalchemy import select

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
