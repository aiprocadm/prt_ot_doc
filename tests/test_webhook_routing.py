from __future__ import annotations

import json
import logging

import httpx
import pytest
from sqlalchemy import select

from app.core.metrics import reset_metrics, sanitize_label
from app.models.models import Tenant, WebhookSubscription
from app.services.webhooks import WebhookDispatcher


async def _tenant_id(session) -> str:
    result = await session.execute(select(Tenant).where(Tenant.slug == "test"))
    tenant = result.scalar_one()
    return tenant.id


@pytest.mark.anyio
async def test_webhook_routes_document_generated(sessionmaker) -> None:
    async with sessionmaker() as session:
        tenant_id = await _tenant_id(session)
        session.add(
            WebhookSubscription(
                tenant_id=tenant_id,
                event_type="DocumentGenerated",
                url="https://example.test/hooks/generated",
                headers={"X-Webhook-Secret": "shh"},
                enabled=True,
            )
        )
        await session.commit()

        requests: list[httpx.Request] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(204)

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            dispatcher = WebhookDispatcher(client=client)
            await dispatcher.dispatch(
                event_type="DocumentGenerated",
                tenant_id=tenant_id,
                payload={"event_id": "evt-1"},
                session=session,
            )

    assert len(requests) == 1
    assert str(requests[0].url) == "https://example.test/hooks/generated"
    assert requests[0].headers.get("X-Webhook-Secret") == "shh"
    body = json.loads(requests[0].content.decode("utf-8"))
    assert body["event_type"] == "DocumentGenerated"


@pytest.mark.anyio
async def test_tenant_specific_overrides_global(sessionmaker) -> None:
    async with sessionmaker() as session:
        tenant_id = await _tenant_id(session)
        session.add(
            WebhookSubscription(
                tenant_id=None,
                event_type="DocumentSigned",
                url="https://example.test/hooks/global",
                headers={},
                enabled=True,
            )
        )
        session.add(
            WebhookSubscription(
                tenant_id=tenant_id,
                event_type="DocumentSigned",
                url="https://example.test/hooks/tenant",
                headers={},
                enabled=True,
            )
        )
        await session.commit()

        requests: list[httpx.Request] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(204)

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            dispatcher = WebhookDispatcher(client=client)
            await dispatcher.dispatch(
                event_type="DocumentSigned",
                tenant_id=tenant_id,
                payload={"event_id": "evt-2"},
                session=session,
            )

    assert len(requests) == 1
    assert str(requests[0].url) == "https://example.test/hooks/tenant"


@pytest.mark.anyio
async def test_no_destination_logs_warning_and_metrics(sessionmaker, caplog) -> None:
    metrics = reset_metrics()
    caplog.set_level(logging.WARNING)

    async with sessionmaker() as session:
        tenant_id = await _tenant_id(session)
        dispatcher = WebhookDispatcher()
        await dispatcher.dispatch(
            event_type="TrainingCompleted",
            tenant_id=tenant_id,
            payload={"event_id": "evt-3"},
            session=session,
        )

    assert any(record.message == "webhook.skip" for record in caplog.records)
    label = sanitize_label("TrainingCompleted")
    assert metrics.outbox_no_destination_total.labels(event_type=label)._value.get() == 1


@pytest.mark.anyio
async def test_disabled_destination_is_ignored(sessionmaker) -> None:
    async with sessionmaker() as session:
        tenant_id = await _tenant_id(session)
        session.add(
            WebhookSubscription(
                tenant_id=tenant_id,
                event_type="RiskAssessed",
                url="https://example.test/hooks/disabled",
                headers={},
                enabled=False,
            )
        )
        session.add(
            WebhookSubscription(
                tenant_id=tenant_id,
                event_type="RiskAssessed",
                url="https://example.test/hooks/enabled",
                headers={},
                enabled=True,
            )
        )
        await session.commit()

        requests: list[httpx.Request] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(204)

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            dispatcher = WebhookDispatcher(client=client)
            await dispatcher.dispatch(
                event_type="RiskAssessed",
                tenant_id=tenant_id,
                payload={"event_id": "evt-4"},
                session=session,
            )

    assert [str(request.url) for request in requests] == [
        "https://example.test/hooks/enabled"
    ]


@pytest.mark.anyio
async def test_multiple_destinations_are_all_called(sessionmaker) -> None:
    async with sessionmaker() as session:
        tenant_id = await _tenant_id(session)
        session.add(
            WebhookSubscription(
                tenant_id=tenant_id,
                event_type="PPEIssued",
                url="https://example.test/hooks/one",
                headers={},
                enabled=True,
            )
        )
        session.add(
            WebhookSubscription(
                tenant_id=tenant_id,
                event_type="PPEIssued",
                url="https://example.test/hooks/two",
                headers={},
                enabled=True,
            )
        )
        await session.commit()

        requests: list[httpx.Request] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(204)

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            dispatcher = WebhookDispatcher(client=client)
            await dispatcher.dispatch(
                event_type="PPEIssued",
                tenant_id=tenant_id,
                payload={"event_id": "evt-5"},
                session=session,
            )

    assert {str(request.url) for request in requests} == {
        "https://example.test/hooks/one",
        "https://example.test/hooks/two",
    }


@pytest.mark.anyio
async def test_invalid_url_is_rejected(sessionmaker, caplog) -> None:
    metrics = reset_metrics()
    caplog.set_level(logging.WARNING)

    async with sessionmaker() as session:
        tenant_id = await _tenant_id(session)
        session.add(
            WebhookSubscription(
                tenant_id=tenant_id,
                event_type="DocumentExported",
                url="not-a-url",
                headers={},
                enabled=True,
            )
        )
        await session.commit()

        requests: list[httpx.Request] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(204)

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            dispatcher = WebhookDispatcher(client=client)
            await dispatcher.dispatch(
                event_type="DocumentExported",
                tenant_id=tenant_id,
                payload={"event_id": "evt-6"},
                session=session,
            )

    assert requests == []
    assert any(record.message == "webhook.invalid_url" for record in caplog.records)
    label = sanitize_label("DocumentExported")
    assert metrics.outbox_no_destination_total.labels(event_type=label)._value.get() == 1
