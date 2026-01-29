from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from time import perf_counter
from typing import Any, Mapping

import httpx
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.metrics import PipelineStage, PipelineType, StageResult, get_metrics
from app.models.models import Outbox, OutboxStatus
from app.services.events import EventType, dedupe_key_for, normalize_payload, resolve_event_type
from app.services.webhooks import WebhookDispatchError, WebhookDispatcher

logger = logging.getLogger(__name__)


def _pipeline_for_event(event_type: str) -> PipelineType:
    resolved = resolve_event_type(event_type)
    if resolved in {
        EventType.DOCUMENT_CREATED,
        EventType.DOCUMENT_SIGNED,
        EventType.DOCUMENT_EXPORTED,
    }:
        return PipelineType.DOCUMENT
    if resolved is EventType.RISK_ASSESSED:
        return PipelineType.RISK
    if resolved in {EventType.PPE_ISSUED, EventType.PPE_RETURNED}:
        return PipelineType.PPE
    if resolved in {EventType.TRAINING_ASSIGNED, EventType.TRAINING_COMPLETED}:
        return PipelineType.TRAINING
    return PipelineType.UNKNOWN


@dataclass(frozen=True, slots=True)
class DispatchResult:
    status: OutboxStatus
    error_class: str | None = None
    error_message: str | None = None
    status_code: int | None = None


class OutboxService:
    """Create outbox entries for outbound delivery."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        dispatcher: WebhookDispatcher | None = None,
    ) -> None:
        self.session = session
        self.metrics = get_metrics()
        self.dispatcher = dispatcher or WebhookDispatcher()

    async def enqueue(
        self,
        *,
        tenant_id: str,
        event_type: str,
        payload: Mapping[str, Any],
        destination: str | None = None,
        headers: Mapping[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> list[Outbox]:
        resolved = resolve_event_type(event_type)
        pipeline = _pipeline_for_event(resolved.value)
        stage_start = perf_counter()
        try:
            payload_model, normalized_payload = normalize_payload(
                event_type=resolved,
                payload=payload,
                tenant_id=tenant_id,
            )
            key = idempotency_key or dedupe_key_for(resolved, payload_model)
            if destination:
                destinations = [destination]
            else:
                destinations = await self.dispatcher.resolve_destinations_for_tenant(
                    event_type=resolved.value,
                    tenant_id=tenant_id,
                    session=self.session,
                )
            if not destinations:
                logger.debug(
                    "outbox.skip_no_destination",
                    extra={"tenant_id": tenant_id, "event_type": resolved.value},
                )
                self.metrics.record_outbox_no_destination(event_type=resolved.value)
                self.metrics.record_pipeline_stage_end(
                    pipeline=pipeline,
                    stage=PipelineStage.OUTBOX_ENQUEUED,
                    result=StageResult.SUCCESS,
                    seconds=perf_counter() - stage_start,
                )
                return []

            created: list[Outbox] = []
            now = datetime.now(tz=timezone.utc)
            for target in destinations:
                existing = None
                if key:
                    existing = await self._find_existing(
                        tenant_id=tenant_id,
                        destination=target,
                        idempotency_key=key,
                    )
                if existing:
                    created.append(existing)
                    continue
                entry = Outbox(
                    tenant_id=tenant_id,
                    event_type=resolved.value,
                    destination=target,
                    payload=normalized_payload,
                    headers=dict(headers) if headers else None,
                    idempotency_key=key,
                    status=OutboxStatus.PENDING,
                    next_attempt_at=now,
                )
                self.session.add(entry)
                await self.session.flush()
                if entry.payload.get("event_id") is None:
                    entry.payload = {**entry.payload, "event_id": entry.id}
                    await self.session.flush()
                created.append(entry)
                self.metrics.record_outbox_enqueued(
                    event_type=entry.event_type,
                    destination=entry.destination,
                    tenant_id=entry.tenant_id,
                )
        except Exception as exc:
            self.metrics.record_pipeline_stage_end(
                pipeline=pipeline,
                stage=PipelineStage.OUTBOX_ENQUEUED,
                result=StageResult.FAILED,
                seconds=perf_counter() - stage_start,
                error_class=exc.__class__.__name__,
            )
            raise

        if created:
            if resolved is EventType.DOCUMENT_CREATED:
                self.metrics.record_document_generated()
            elif resolved is EventType.DOCUMENT_SIGNED:
                self.metrics.record_document_signed()
            elif resolved is EventType.RISK_ASSESSED:
                self.metrics.record_risk_assessed()
            elif resolved is EventType.PPE_ISSUED:
                self.metrics.record_ppe_issued()
            elif resolved is EventType.TRAINING_COMPLETED:
                self.metrics.record_training_completed()

        self.metrics.record_pipeline_stage_end(
            pipeline=pipeline,
            stage=PipelineStage.OUTBOX_ENQUEUED,
            result=StageResult.SUCCESS,
            seconds=perf_counter() - stage_start,
        )
        return created

    async def _find_existing(
        self,
        *,
        tenant_id: str,
        destination: str,
        idempotency_key: str,
    ) -> Outbox | None:
        stmt = select(Outbox).where(
            Outbox.tenant_id == tenant_id,
            Outbox.destination == destination,
            Outbox.idempotency_key == idempotency_key,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


class OutboxProcessor:
    def __init__(
        self,
        session: AsyncSession,
        *,
        dispatcher: WebhookDispatcher | None = None,
    ) -> None:
        self.session = session
        self.settings = get_settings()
        self.dispatcher = dispatcher or WebhookDispatcher()
        self.metrics = get_metrics()

    async def run(self) -> None:
        while True:
            await self.process_once()
            await asyncio.sleep(self.settings.outbox_poll_interval)

    async def process_once(self, *, batch_size: int = 100) -> int:
        start_loop = perf_counter()
        now = datetime.now(tz=timezone.utc)
        stmt: Select[tuple[Outbox]] = (
            select(Outbox)
            .where(
                Outbox.status.in_([OutboxStatus.PENDING, OutboxStatus.FAILED]),
                Outbox.next_attempt_at.is_not(None),
                Outbox.next_attempt_at <= now,
            )
            .order_by(Outbox.next_attempt_at.asc(), Outbox.created_at.asc())
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        )
        result = await self.session.execute(stmt)
        entries = result.scalars().all()
        if not entries:
            self.metrics.record_outbox_dispatcher_tick(processed=0)
            self.metrics.observe_outbox_dispatcher_duration(seconds=perf_counter() - start_loop)
            return 0

        for entry in entries:
            entry.status = OutboxStatus.IN_PROGRESS
            entry.attempts += 1

        await self.session.commit()

        processed = 0
        for entry in entries:
            if entry.attempts > self.settings.outbox_max_attempts:
                await self._mark_dead(entry, reason="max_attempts_exceeded")
                self.metrics.record_outbox_dead(
                    event_type=entry.event_type,
                    destination=entry.destination,
                )
                self.metrics.record_outbox_failed(
                    event_type=entry.event_type,
                    destination=entry.destination,
                    error_class="max_attempts_exceeded",
                )
                continue

            self.metrics.observe_outbox_attempts(
                event_type=entry.event_type,
                destination=entry.destination,
                attempts=entry.attempts,
            )
            pipeline = _pipeline_for_event(entry.event_type)
            stage_start = perf_counter()
            self.metrics.record_pipeline_stage_start(
                pipeline=pipeline,
                stage=PipelineStage.WEBHOOK_DISPATCHED,
            )
            result = await self._dispatch_entry(entry)
            duration = perf_counter() - stage_start

            if result.status == OutboxStatus.SENT:
                await self._mark_sent(entry)
                processed += 1
                self.metrics.record_outbox_sent(
                    event_type=entry.event_type,
                    destination=entry.destination,
                )
                latency = (entry.sent_at or datetime.now(tz=timezone.utc)) - entry.created_at
                self.metrics.observe_outbox_dispatch_latency(
                    event_type=entry.event_type,
                    destination=entry.destination,
                    seconds=latency.total_seconds(),
                )
                self.metrics.record_pipeline_stage_end(
                    pipeline=pipeline,
                    stage=PipelineStage.WEBHOOK_DISPATCHED,
                    result=StageResult.SUCCESS,
                    seconds=duration,
                )
                logger.info(
                    "outbox.dispatch_attempt",
                    extra={
                        "outbox_id": entry.id,
                        "tenant_id": entry.tenant_id,
                        "event_type": entry.event_type,
                        "destination": entry.destination,
                        "attempt": entry.attempts,
                        "status": "sent",
                        "duration_seconds": duration,
                    },
                )
                continue

            if result.status == OutboxStatus.DEAD:
                await self._mark_dead(entry, result)
                self.metrics.record_outbox_dead(
                    event_type=entry.event_type,
                    destination=entry.destination,
                )
            else:
                await self._mark_failed(entry, result)
                self.metrics.record_outbox_failed(
                    event_type=entry.event_type,
                    destination=entry.destination,
                    error_class=result.error_class or "unknown",
                )

            self.metrics.record_pipeline_stage_end(
                pipeline=pipeline,
                stage=PipelineStage.WEBHOOK_DISPATCHED,
                result=StageResult.FAILED,
                seconds=duration,
                error_class=result.error_class or "unknown",
            )

            logger.warning(
                "outbox.dispatch_attempt",
                extra={
                    "outbox_id": entry.id,
                    "tenant_id": entry.tenant_id,
                    "event_type": entry.event_type,
                    "destination": entry.destination,
                    "attempt": entry.attempts,
                    "status": result.status.value,
                    "error": result.error_message,
                    "error_class": result.error_class,
                    "status_code": result.status_code,
                    "duration_seconds": duration,
                },
            )

        if entries:
            await self.session.commit()

        self.metrics.record_outbox_dispatcher_tick(processed=processed)
        self.metrics.observe_outbox_dispatcher_duration(seconds=perf_counter() - start_loop)
        return processed

    async def _dispatch_entry(self, entry: Outbox) -> DispatchResult:
        try:
            await self.dispatcher.dispatch(
                event_type=entry.event_type,
                tenant_id=entry.tenant_id,
                payload=dict(entry.payload or {}),
                destination=entry.destination,
                headers=entry.headers or {},
                idempotency_key=entry.idempotency_key,
                session=self.session,
            )
        except WebhookDispatchError as exc:
            classification = self._classify_http_error(exc.status_code)
            return DispatchResult(
                status=classification,
                error_class=exc.error_class,
                error_message=str(exc),
                status_code=exc.status_code,
            )
        except httpx.TimeoutException as exc:
            return DispatchResult(
                status=OutboxStatus.FAILED,
                error_class="timeout",
                error_message=str(exc),
            )
        except httpx.RequestError as exc:
            return DispatchResult(
                status=OutboxStatus.FAILED,
                error_class="connection",
                error_message=str(exc),
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception(
                "outbox.dispatch_unhandled",
                extra={"outbox_id": entry.id, "event_type": entry.event_type},
            )
            return DispatchResult(
                status=OutboxStatus.FAILED,
                error_class=exc.__class__.__name__ or "error",
                error_message=str(exc),
            )
        return DispatchResult(status=OutboxStatus.SENT)

    def _classify_http_error(self, status_code: int | None) -> OutboxStatus:
        if status_code is None:
            return OutboxStatus.FAILED
        if status_code >= 500 or status_code in {408, 429}:
            return OutboxStatus.FAILED
        return OutboxStatus.DEAD

    def _compute_next_attempt(self, attempt: int) -> datetime:
        base = self.settings.outbox_retry_backoff_seconds
        cap = self.settings.outbox_retry_backoff_max_seconds
        exponent = max(attempt - 1, 0)
        jitter = random.random() * base
        delay = min(base * (2**exponent) + jitter, cap)
        return datetime.now(tz=timezone.utc) + timedelta(seconds=delay)

    async def _mark_sent(self, entry: Outbox) -> None:
        entry.status = OutboxStatus.SENT
        entry.sent_at = datetime.now(tz=timezone.utc)
        entry.next_attempt_at = None
        entry.last_error = None

    async def _mark_failed(self, entry: Outbox, result: DispatchResult) -> None:
        entry.status = OutboxStatus.FAILED
        entry.next_attempt_at = self._compute_next_attempt(entry.attempts)
        entry.last_error = self._error_payload(result)

    async def _mark_dead(
        self,
        entry: Outbox,
        result: DispatchResult | None = None,
        *,
        reason: str | None = None,
    ) -> None:
        entry.status = OutboxStatus.DEAD
        entry.next_attempt_at = None
        payload = self._error_payload(result) if result else None
        if reason:
            payload = {"message": reason, "error_class": reason}
        entry.last_error = payload

    def _error_payload(self, result: DispatchResult | None) -> dict[str, Any] | None:
        if result is None:
            return None
        payload: dict[str, Any] = {}
        if result.error_class:
            payload["error_class"] = result.error_class
        if result.error_message:
            payload["message"] = result.error_message
        if result.status_code is not None:
            payload["status_code"] = result.status_code
        return payload or None
