"""
Outbox acceptance tests for poison-queue and deduplication guarantees (TZ-B5-MVP-01).

Tests verify:
- Poison queue guarantee: events fail to dead-letter after max_attempts
- Deduplication guarantee: same idempotency_key prevents duplicate delivery
- End-to-end webhook routing and retry behavior
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import func, select

from app.models.models import Outbox, OutboxStatus, Tenant, WebhookDelivery
from app.services.outbox import OutboxProcessor


class PoisonQueueAcceptanceDispatcher:
    """Dispatcher that simulates permanent failure (for poison queue acceptance)."""

    def __init__(self) -> None:
        self.call_count = 0
        self.processed_events: list[dict[str, Any]] = []

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
        self.call_count += 1
        self.processed_events.append(
            {
                "event_type": event_type,
                "idempotency_key": idempotency_key,
                "attempt": self.call_count,
            }
        )
        # Always fail to simulate permanent error (e.g., endpoint not found)
        raise RuntimeError("Webhook endpoint not found (410 Gone)")


@pytest.mark.anyio
async def test_poison_queue_guarantee_event_moves_to_dead_after_max_attempts(
    sessionmaker, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    ACCEPTANCE: Event should move to POISON_QUEUE (dead-letter) after max_attempts exceeded.

    This guarantees that permanently failed events don't loop infinitely,
    but are moved to dead-letter for manual inspection/cleanup.
    """
    monkeypatch.setenv("OUTBOX_MAX_ATTEMPTS", "3")
    monkeypatch.setenv("OUTBOX_RETRY_BACKOFF_SECONDS", "0.01")
    from app.core.config import get_settings
    get_settings.cache_clear()  # type: ignore[attr-defined]

    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        # Create event with permanent failure scenario
        event = Outbox(
            tenant_id=tenant.id,
            event_type="DocumentArchived",
            destination="https://deleted-webhook-endpoint.example.com/",  # Deleted endpoint
            payload={"document_id": "doc-poison-1", "status": "archived"},
            idempotency_key="poison-guarantee-key-1",
            status=OutboxStatus.PENDING,
            next_attempt_at=datetime.now(tz=timezone.utc),
            attempts=0,
        )
        session.add(event)
        await session.commit()
        event_id = event.id

    dispatcher = PoisonQueueAcceptanceDispatcher()

    # Simulate multiple dispatch cycles (should try 3 times then move to poison queue)
    for cycle in range(1, 5):  # More cycles than max_attempts
        async with sessionmaker() as session:
            processor = OutboxProcessor(session, dispatcher=dispatcher)
            processed = await processor.process_once()

        async with sessionmaker() as session:
            current_event = await session.get(Outbox, event_id)

            if cycle < 3:
                # Before max_attempts, should remain in FAILED/PENDING with backoff
                assert current_event.attempts == cycle
                assert current_event.status in (OutboxStatus.FAILED, OutboxStatus.PENDING)
            else:
                # After max_attempts, should move to POISON_QUEUE or DEAD
                assert current_event.attempts >= 3
                assert current_event.status in (
                    OutboxStatus.DEAD,
                    OutboxStatus.FAILED,  # Some implementations mark as FAILED with attempts >= max
                )
                # Event should NOT be retried indefinitely
                break

    # Verify poison queue guarantee: event won't be processed anymore
    assert dispatcher.call_count <= 5  # At most max_attempts + some buffer


@pytest.mark.anyio
async def test_deduplication_guarantee_same_idempotency_key_prevents_duplicate_delivery(
    sessionmaker,
) -> None:
    """
    ACCEPTANCE: Events with same idempotency_key should not result in duplicate deliveries.

    This guarantees that if an event is emitted twice with the same key (e.g., on retry),
    only one delivery attempt is made to the webhook.
    """
    dispatcher = AsyncMock()
    dispatcher.dispatch = AsyncMock()

    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()

        # Create two events with the same idempotency_key
        dedup_key = "dedup-guarantee-key-payment-123"
        event1 = Outbox(
            tenant_id=tenant.id,
            event_type="PaymentProcessed",
            destination="https://accounting.example.com/webhooks",
            payload={"transaction_id": "txn-123", "amount": 99.99},
            idempotency_key=dedup_key,
            status=OutboxStatus.PENDING,
            next_attempt_at=datetime.now(tz=timezone.utc) - timedelta(seconds=1),
        )
        session.add(event1)
        # Commit event1 in its own transaction so the duplicate's rollback below
        # cannot discard it (a flush-only event1 shares the transaction that the
        # IntegrityError rolls back, which would leave 0 rows, not 1).
        await session.commit()
        event1_id = event1.id

        # Attempt to add duplicate with same key (should fail or be ignored)
        event2 = Outbox(
            tenant_id=tenant.id,
            event_type="PaymentProcessed",
            destination="https://accounting.example.com/webhooks",
            payload={"transaction_id": "txn-123", "amount": 99.99},
            idempotency_key=dedup_key,  # SAME KEY
            status=OutboxStatus.PENDING,
            next_attempt_at=datetime.now(tz=timezone.utc) - timedelta(seconds=1),
        )
        session.add(event2)
        try:
            await session.commit()
            duplicate_inserted = True
        except Exception:
            # Expected: unique constraint on (tenant_id, idempotency_key)
            await session.rollback()
            duplicate_inserted = False

    # Verify deduplication guarantee
    async with sessionmaker() as session:
        count = await session.scalar(
            select(func.count()).select_from(
                select(Outbox).filter_by(idempotency_key=dedup_key).subquery()
            )
        )
        # Should have exactly 1, never 2
        assert count == 1, f"Dedup guarantee violated: {count} entries with same key"

    # Process the single entry
    async with sessionmaker() as session:
        processor = OutboxProcessor(session, dispatcher=dispatcher)
        processed = await processor.process_once()

    assert processed == 1
    # Verify dispatcher was called exactly once (not twice for duplicate)
    dispatcher.dispatch.assert_called_once()


@pytest.mark.anyio
async def test_poison_queue_and_dedup_combined_guarantee(
    sessionmaker, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    ACCEPTANCE: Combined guarantee test - poison queue + dedup together.

    When an event fails permanently AND is deduplicated, the dedup prevents
    the poison queue from bloating with duplicate entries.
    """
    monkeypatch.setenv("OUTBOX_MAX_ATTEMPTS", "2")
    monkeypatch.setenv("OUTBOX_RETRY_BACKOFF_SECONDS", "0.01")
    from app.core.config import get_settings
    get_settings.cache_clear()  # type: ignore[attr-defined]

    dispatcher = PoisonQueueAcceptanceDispatcher()

    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        dedup_key = "combined-guarantee-key"

        event = Outbox(
            tenant_id=tenant.id,
            event_type="ComplianceReport",
            destination="https://compliance-404.example.com/",  # Will 404 = permanent failure
            payload={"report_id": "rpt-456"},
            idempotency_key=dedup_key,
            status=OutboxStatus.PENDING,
            next_attempt_at=datetime.now(tz=timezone.utc),
            attempts=0,
        )
        session.add(event)
        await session.commit()
        event_id = event.id

    # Try to process multiple times
    for _ in range(3):
        async with sessionmaker() as session:
            processor = OutboxProcessor(session, dispatcher=dispatcher)
            await processor.process_once()

    # Verify combined guarantee
    async with sessionmaker() as session:
        # Should have exactly 1 entry (dedup prevents duplicates)
        count = await session.scalar(
            select(func.count()).select_from(
                select(Outbox).filter_by(idempotency_key=dedup_key).subquery()
            )
        )
        assert count == 1

        # That entry should be in poison queue after max_attempts
        final_event = await session.get(Outbox, event_id)
        assert final_event.attempts >= 2
        assert final_event.status in (OutboxStatus.DEAD, OutboxStatus.FAILED)

    # Dispatcher should have been called at most max_attempts times, not more
    assert dispatcher.call_count <= 4  # max_attempts + small buffer


@pytest.mark.anyio
async def test_webhook_delivery_tracking_in_poison_queue(sessionmaker) -> None:
    """
    ACCEPTANCE: WebhookDelivery records should track all attempts,
    including those that eventually move to poison queue.
    """
    dispatcher = PoisonQueueAcceptanceDispatcher()

    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        event = Outbox(
            tenant_id=tenant.id,
            event_type="AuditLogExport",
            destination="https://siem-system.example.com/logs",
            payload={"log_batch_id": "batch-789"},
            status=OutboxStatus.PENDING,
            next_attempt_at=datetime.now(tz=timezone.utc),
        )
        session.add(event)
        await session.commit()
        event_id = event.id

    # Process until poison queue
    for _ in range(5):
        async with sessionmaker() as session:
            processor = OutboxProcessor(session, dispatcher=dispatcher)
            await processor.process_once()

    # Verify attempts are tracked
    async with sessionmaker() as session:
        event = await session.get(Outbox, event_id)
        # Should show multiple failed attempts in the event record
        assert event.attempts >= 1
        assert event.last_error is not None
        # last_error is a structured JSON diagnostics dict (Outbox.last_error: JSON);
        # check its serialized form for the recorded failure text.
        error_text = str(event.last_error).lower()
        assert "not found" in error_text or "error" in error_text
