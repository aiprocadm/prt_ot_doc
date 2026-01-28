from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Mapping

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from time import perf_counter

from app.core.config import get_settings
from app.core.metrics import PipelineStage, PipelineType, StageResult, get_metrics
from app.models.models import Outbox
from app.services.events import EventType, dedupe_key_for, normalize_payload, resolve_event_type
from app.services.webhooks import WebhookDispatcher

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


class OutboxService:
    """Create outbox entries for webhook delivery."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.metrics = get_metrics()

    async def enqueue(
        self,
        *,
        tenant_id: str,
        event_type: str,
        payload: Mapping[str, Any],
        dedupe_key: str | None = None,
    ) -> Outbox:
        resolved = resolve_event_type(event_type)
        stage_start = perf_counter()
        pipeline = _pipeline_for_event(resolved.value)
        self.metrics.record_pipeline_stage_start(
            pipeline=pipeline,
            stage=PipelineStage.OUTBOX_ENQUEUED,
        )
        created = False
        try:
            payload_model, normalized_payload = normalize_payload(
                event_type=resolved,
                payload=payload,
                tenant_id=tenant_id,
            )
            key = dedupe_key or dedupe_key_for(resolved, payload_model)
            entry: Outbox | None = None
            if key:
                existing = await self._find_existing(
                    tenant_id=tenant_id,
                    event_type=resolved.value,
                    dedupe_key=key,
                )
                if existing:
                    entry = existing
            if entry is None:
                entry = Outbox(
                    tenant_id=tenant_id,
                    event_type=resolved.value,
                    payload=normalized_payload,
                    dedupe_key=key,
                )
                self.session.add(entry)
                await self.session.flush()
                if entry.payload.get("event_id") is None:
                    entry.payload = {**entry.payload, "event_id": entry.id}
                    await self.session.flush()
                created = True
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

        self.metrics.record_outbox_enqueued(event_type=entry.event_type)
        self.metrics.record_pipeline_stage_end(
            pipeline=pipeline,
            stage=PipelineStage.OUTBOX_ENQUEUED,
            result=StageResult.SUCCESS,
            seconds=perf_counter() - stage_start,
        )
        return entry

    async def _find_existing(
        self,
        *,
        tenant_id: str,
        event_type: str,
        dedupe_key: str,
    ) -> Outbox | None:
        stmt = select(Outbox).where(
            Outbox.tenant_id == tenant_id,
            Outbox.event_type == event_type,
            Outbox.dedupe_key == dedupe_key,
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

    async def process_once(self) -> int:
        stmt = (
            select(Outbox)
            .where(Outbox.processed_at.is_(None))
            .order_by(Outbox.created_at.asc())
            .limit(100)
        )
        result = await self.session.execute(stmt)
        entries = result.scalars().all()
        processed = 0
        for entry in entries:
            logger.info(
                "outbox.dispatch",
                extra={"event_type": entry.event_type, "outbox_id": entry.id},
            )
            entry.attempts += 1
            if entry.attempts > self.settings.outbox_max_attempts:
                entry.processed_at = datetime.now(tz=timezone.utc)
                entry.last_error = "max_attempts_exceeded"
                logger.warning(
                    "outbox.discarded",
                    extra={
                        "event_type": entry.event_type,
                        "outbox_id": entry.id,
                        "attempts": entry.attempts,
                    },
                )
                continue
            try:
                pipeline = _pipeline_for_event(entry.event_type)
                stage_start = perf_counter()
                self.metrics.record_pipeline_stage_start(
                    pipeline=pipeline,
                    stage=PipelineStage.WEBHOOK_DISPATCHED,
                )
                await self.dispatcher.dispatch(
                    event_type=entry.event_type,
                    tenant_id=entry.tenant_id,
                    payload=dict(entry.payload or {}),
                    session=self.session,
                )
            except Exception as exc:
                entry.last_error = str(exc)
                self.metrics.record_pipeline_stage_end(
                    pipeline=pipeline,
                    stage=PipelineStage.WEBHOOK_DISPATCHED,
                    result=StageResult.FAILED,
                    seconds=perf_counter() - stage_start,
                    error_class=exc.__class__.__name__,
                )
                logger.warning(
                    "outbox.dispatch_failed",
                    extra={
                        "event_type": entry.event_type,
                        "outbox_id": entry.id,
                        "error": str(exc),
                    },
                )
                continue
            entry.processed_at = datetime.now(tz=timezone.utc)
            entry.last_error = None
            self.metrics.record_pipeline_stage_end(
                pipeline=pipeline,
                stage=PipelineStage.WEBHOOK_DISPATCHED,
                result=StageResult.SUCCESS,
                seconds=perf_counter() - stage_start,
            )
            processed += 1
        if entries:
            await self.session.commit()
        return processed
