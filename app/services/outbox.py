from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Mapping

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from time import perf_counter

from app.core.config import get_settings
from app.core.metrics import get_metrics
from app.models.models import Outbox
from app.services.webhooks import WebhookDispatcher

logger = logging.getLogger(__name__)


class OutboxService:
    """Create outbox entries for webhook delivery."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def enqueue(
        self,
        *,
        tenant_id: str,
        event_type: str,
        payload: Mapping[str, Any],
    ) -> Outbox:
        entry = Outbox(
            tenant_id=tenant_id,
            event_type=event_type,
            payload=dict(payload),
        )
        self.session.add(entry)
        await self.session.flush()
        if entry.payload.get("event_id") is None:
            entry.payload = {**entry.payload, "event_id": entry.id}
            await self.session.flush()
        return entry


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
            start = perf_counter()
            try:
                await self.dispatcher.dispatch(
                    event_type=entry.event_type,
                    tenant_id=entry.tenant_id,
                    payload=dict(entry.payload or {}),
                )
            except Exception as exc:
                entry.last_error = str(exc)
                duration = perf_counter() - start
                self.metrics.observe_pipeline_stage(
                    stage="webhook_dispatch",
                    status="error",
                    seconds=duration,
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
            duration = perf_counter() - start
            self.metrics.observe_pipeline_stage(
                stage="webhook_dispatch",
                status="success",
                seconds=duration,
            )
            processed += 1
        if entries:
            await self.session.commit()
        return processed
