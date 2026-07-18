from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.models.models import Outbox, OutboxStatus, Tenant, WebhookDelivery
from app.services.outbox import OutboxProcessor


class DummyDispatcher:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def dispatch(
        self,
        *,
        event_type: str,
        tenant_id: str,
        payload: dict,
        destination: str,
        headers: dict | None = None,
        idempotency_key: str | None = None,
        session=None,
    ) -> None:
        self.calls.append(
            {
                "event_type": event_type,
                "tenant_id": tenant_id,
                "payload": payload,
                "destination": destination,
                "headers": headers or {},
                "idempotency_key": idempotency_key,
            }
        )
        if payload.get("fail"):
            raise RuntimeError("boom")


class BlockingDispatcher:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.calls = 0

    async def dispatch(
        self,
        *,
        event_type: str,
        tenant_id: str,
        payload: dict,
        destination: str,
        headers: dict | None = None,
        idempotency_key: str | None = None,
    ) -> None:
        self.calls += 1
        self.started.set()
        await self.release.wait()


@pytest.mark.anyio
async def test_outbox_processor_dispatches_entries(sessionmaker) -> None:
    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        entry = Outbox(
            tenant_id=tenant.id,
            event_type="DocumentCreated",
            destination="https://example.test/hooks",
            payload={"document_id": "doc-1"},
            status=OutboxStatus.PENDING,
            next_attempt_at=datetime.now(tz=timezone.utc) - timedelta(seconds=1),
        )
        session.add(entry)
        await session.commit()
        entry_id = entry.id

    dispatcher = DummyDispatcher()
    async with sessionmaker() as session:
        processor = OutboxProcessor(session, dispatcher=dispatcher)
        processed = await processor.process_once()

    assert processed == 1
    assert dispatcher.calls
    assert dispatcher.calls[0]["event_type"] == "DocumentCreated"

    async with sessionmaker() as session:
        refreshed = await session.get(Outbox, entry_id)
        assert refreshed is not None
        assert refreshed.sent_at is not None
        assert refreshed.attempts == 1
        assert refreshed.last_error is None
        assert refreshed.status == OutboxStatus.SENT


@pytest.mark.anyio
async def test_outbox_processor_retries_failed_entries(
    sessionmaker, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OUTBOX_RETRY_BACKOFF_SECONDS", "1")
    monkeypatch.setenv("OUTBOX_RETRY_BACKOFF_MAX_SECONDS", "5")
    get_settings.cache_clear()  # type: ignore[attr-defined]

    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        entry = Outbox(
            tenant_id=tenant.id,
            event_type="DocumentSigned",
            destination="https://example.test/hooks",
            payload={"document_id": "doc-2", "fail": True},
            status=OutboxStatus.PENDING,
            next_attempt_at=datetime.now(tz=timezone.utc) - timedelta(seconds=1),
        )
        session.add(entry)
        await session.commit()
        entry_id = entry.id

    dispatcher = DummyDispatcher()
    async with sessionmaker() as session:
        processor = OutboxProcessor(session, dispatcher=dispatcher)
        processed = await processor.process_once()

    assert processed == 0
    assert dispatcher.calls

    async with sessionmaker() as session:
        refreshed = await session.get(Outbox, entry_id)
        assert refreshed is not None
        assert refreshed.sent_at is None
        assert refreshed.attempts == 1
        assert refreshed.last_error
        assert refreshed.status == OutboxStatus.FAILED
        assert refreshed.next_attempt_at is not None
        assert refreshed.next_attempt_at > refreshed.created_at

    get_settings.cache_clear()  # type: ignore[attr-defined]


@pytest.mark.anyio
async def test_outbox_processor_dead_letters_after_max_attempts(
    sessionmaker, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OUTBOX_MAX_ATTEMPTS", "1")
    get_settings.cache_clear()  # type: ignore[attr-defined]

    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        entry = Outbox(
            tenant_id=tenant.id,
            event_type="DocumentCreated",
            destination="https://example.test/hooks",
            payload={"document_id": "doc-3"},
            attempts=1,
            status=OutboxStatus.PENDING,
            next_attempt_at=datetime.now(tz=timezone.utc) - timedelta(seconds=1),
        )
        session.add(entry)
        await session.commit()
        entry_id = entry.id

    dispatcher = DummyDispatcher()
    async with sessionmaker() as session:
        processor = OutboxProcessor(session, dispatcher=dispatcher)
        processed = await processor.process_once()

    assert processed == 0
    assert dispatcher.calls == []

    async with sessionmaker() as session:
        refreshed = await session.get(Outbox, entry_id)
        assert refreshed is not None
        assert refreshed.sent_at is None
        assert refreshed.attempts == 2
        assert refreshed.last_error
        assert refreshed.status == OutboxStatus.DEAD

    get_settings.cache_clear()  # type: ignore[attr-defined]


@pytest.mark.anyio
async def test_outbox_processor_avoids_double_send_with_in_progress(
    sessionmaker,
) -> None:
    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        entry = Outbox(
            tenant_id=tenant.id,
            event_type="DocumentCreated",
            destination="https://example.test/hooks",
            payload={"document_id": "doc-4"},
            status=OutboxStatus.PENDING,
            next_attempt_at=datetime.now(tz=timezone.utc) - timedelta(seconds=1),
        )
        session.add(entry)
        await session.commit()

    dispatcher = BlockingDispatcher()

    async def run_first() -> int:
        async with sessionmaker() as session:
            processor = OutboxProcessor(session, dispatcher=dispatcher)
            return await processor.process_once()

    task = asyncio.create_task(run_first())
    await dispatcher.started.wait()

    async with sessionmaker() as session:
        processor = OutboxProcessor(session, dispatcher=dispatcher)
        processed = await processor.process_once()

    dispatcher.release.set()
    first_processed = await task

    assert first_processed == 1
    assert processed == 0
    assert dispatcher.calls == 1


@pytest.mark.anyio
async def test_outbox_processor_reclaims_stale_in_progress_entries(
    sessionmaker, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OUTBOX_IN_PROGRESS_TIMEOUT_SECONDS", "1")
    get_settings.cache_clear()  # type: ignore[attr-defined]

    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        entry = Outbox(
            tenant_id=tenant.id,
            event_type="DocumentCreated",
            destination="https://example.test/hooks",
            payload={"document_id": "doc-stale"},
            status=OutboxStatus.IN_PROGRESS,
            attempts=1,
            next_attempt_at=None,
            updated_at=datetime.now(tz=timezone.utc) - timedelta(seconds=5),
        )
        session.add(entry)
        await session.commit()
        entry_id = entry.id

    dispatcher = DummyDispatcher()
    async with sessionmaker() as session:
        processor = OutboxProcessor(session, dispatcher=dispatcher)
        processed = await processor.process_once()

    assert processed == 1
    assert len(dispatcher.calls) == 1

    async with sessionmaker() as session:
        refreshed = await session.get(Outbox, entry_id)
        assert refreshed is not None
        assert refreshed.status == OutboxStatus.SENT
        assert refreshed.attempts == 2
        assert refreshed.sent_at is not None

    get_settings.cache_clear()  # type: ignore[attr-defined]


@pytest.mark.anyio
async def test_outbox_dedup_prevents_second_delivery(sessionmaker) -> None:
    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        entry = Outbox(
            tenant_id=tenant.id,
            event_type="DocumentCreated",
            destination="https://example.test/hooks",
            payload={"event_id": "evt-dedup", "document_id": "doc-9"},
            headers={"X-Webhook-Subscription-Id": "sub-1"},
            status=OutboxStatus.PENDING,
            next_attempt_at=datetime.now(tz=timezone.utc) - timedelta(seconds=1),
        )
        session.add(entry)
        session.add(
            WebhookDelivery(
                tenant_id=tenant.id,
                endpoint_id="sub-1",
                event_id="evt-dedup",
                status="success",
                attempts=1,
            )
        )
        await session.commit()

    dispatcher = DummyDispatcher()
    async with sessionmaker() as session:
        processor = OutboxProcessor(session, dispatcher=dispatcher)
        processed = await processor.process_once()

    assert processed == 1
    assert dispatcher.calls == []


@pytest.mark.anyio
async def test_classify_http_error_rules(sessionmaker) -> None:
    async with sessionmaker() as session:
        processor = OutboxProcessor(session)
        assert processor._classify_http_error(500) == OutboxStatus.FAILED
        assert processor._classify_http_error(429) == OutboxStatus.FAILED
        assert processor._classify_http_error(408) == OutboxStatus.FAILED
        assert processor._classify_http_error(404) == OutboxStatus.DEAD


@pytest.mark.anyio
async def test_backoff_is_bounded(sessionmaker, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OUTBOX_RETRY_BACKOFF_SECONDS", "1")
    monkeypatch.setenv("OUTBOX_RETRY_BACKOFF_MAX_SECONDS", "2")
    get_settings.cache_clear()  # type: ignore[attr-defined]

    async with sessionmaker() as session:
        processor = OutboxProcessor(session)
        delta = (
            processor._compute_next_attempt(10) - datetime.now(tz=timezone.utc)
        ).total_seconds()
        assert delta <= 2.1
        assert delta >= 0.9

    get_settings.cache_clear()  # type: ignore[attr-defined]
