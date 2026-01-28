from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.metrics import Metrics, get_metrics
from app.core.tracing import get_trace_id
from app.models.models import WebhookSubscription

logger = logging.getLogger(__name__)


class WebhookDispatchError(RuntimeError):
    """Raised when a webhook cannot be delivered successfully."""


@dataclass(slots=True)
class WebhookDispatcher:
    """Dispatch webhook events to configured endpoints."""

    settings: Settings
    client: httpx.AsyncClient | None = None
    metrics: Metrics

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.client = client
        self.metrics = get_metrics()

    def _resolve_urls(self, event_type: str) -> list[str]:
        urls_by_event: dict[str, Iterable[str]] = {
            "DocumentCreated": (
                self.settings.webhook_document_created_urls
                or self.settings.webhook_document_generated_urls
            ),
            "DocumentGenerated": (
                self.settings.webhook_document_generated_urls
                or self.settings.webhook_document_created_urls
            ),
            "DocumentSigned": (
                self.settings.webhook_document_signed_urls
                or self.settings.webhook_signed_urls
            ),
            "DocumentExported": (
                self.settings.webhook_document_exported_urls
                or self.settings.webhook_exported_urls
            ),
            "RiskAssessed": self.settings.webhook_risk_assessed_urls,
            "PPEIssued": self.settings.webhook_ppe_issued_urls,
            "PPEReturned": self.settings.webhook_ppe_returned_urls,
            "TrainingCompleted": self.settings.webhook_training_completed_urls,
            "TrainingAssigned": self.settings.webhook_training_assigned_urls,
        }
        return list(urls_by_event.get(event_type, ()))

    @staticmethod
    def _validate_url(url: str) -> bool:
        parsed = urlparse(url)
        return parsed.scheme in {"http", "https"} and bool(parsed.hostname)

    async def _resolve_db_destinations(
        self,
        *,
        session: AsyncSession,
        event_type: str,
        tenant_id: str,
    ) -> list[WebhookSubscription]:
        base_stmt = select(WebhookSubscription).where(
            WebhookSubscription.event_type == event_type,
            WebhookSubscription.enabled.is_(True),
        )
        tenant_stmt = base_stmt.where(WebhookSubscription.tenant_id == tenant_id).order_by(
            WebhookSubscription.created_at.asc()
        )
        tenant_result = await session.execute(tenant_stmt)
        tenant_rows = tenant_result.scalars().all()
        if tenant_rows:
            return tenant_rows

        global_stmt = base_stmt.where(WebhookSubscription.tenant_id.is_(None)).order_by(
            WebhookSubscription.created_at.asc()
        )
        global_result = await session.execute(global_stmt)
        return global_result.scalars().all()

    def _build_destinations_from_urls(
        self,
        *,
        event_type: str,
        urls: Iterable[str],
    ) -> list[WebhookDestination]:
        destinations: list[WebhookDestination] = []
        for url in urls:
            if not self._validate_url(url):
                logger.warning(
                    "webhook.invalid_url",
                    extra={"event_type": event_type, "url": url},
                )
                continue
            destinations.append(WebhookDestination(url=url, headers={}))
        return destinations

    def _build_destinations_from_rows(
        self,
        *,
        event_type: str,
        rows: Iterable[WebhookSubscription],
    ) -> list[WebhookDestination]:
        destinations: list[WebhookDestination] = []
        for row in rows:
            if not self._validate_url(row.url):
                logger.warning(
                    "webhook.invalid_url",
                    extra={"event_type": event_type, "url": row.url},
                )
                continue
            destinations.append(
                WebhookDestination(
                    url=row.url,
                    headers={str(key): str(value) for key, value in (row.headers or {}).items()},
                )
            )
        return destinations

    async def _resolve_destinations(
        self,
        *,
        event_type: str,
        tenant_id: str,
        session: AsyncSession | None,
    ) -> list[WebhookDestination]:
        if session is not None:
            rows = await self._resolve_db_destinations(
                session=session,
                event_type=event_type,
                tenant_id=tenant_id,
            )
            if rows:
                return self._build_destinations_from_rows(event_type=event_type, rows=rows)
        return self._build_destinations_from_urls(
            event_type=event_type,
            urls=self._resolve_urls(event_type),
        )

    async def dispatch(
        self,
        *,
        event_type: str,
        tenant_id: str,
        payload: dict,
        session: AsyncSession | None = None,
    ) -> None:
        destinations = await self._resolve_destinations(
            event_type=event_type,
            tenant_id=tenant_id,
            session=session,
        )
        if not destinations:
            logger.warning(
                "webhook.skip",
                extra={"event_type": event_type, "tenant_id": tenant_id},
            )
            self.metrics.record_outbox_no_destination(event_type=event_type)
            return

        trace_id = get_trace_id()
        envelope = {
            "event_type": event_type,
            "tenant_id": tenant_id,
            "sent_at": datetime.now(tz=timezone.utc).isoformat(),
            "payload": payload,
        }
        headers = {"X-Correlation-ID": trace_id}
        event_id = payload.get("event_id")
        if event_id:
            headers["Idempotency-Key"] = str(event_id)

        failures: list[str] = []
        async with httpx.AsyncClient(
            timeout=self.settings.webhook_timeout_seconds
        ) if self.client is None else _null_async_context(self.client) as client:
            for destination in destinations:
                self.metrics.record_outbox_routed(
                    event_type=event_type, destination=destination.url
                )
                request_headers = {**headers, **destination.headers}
                response = await client.post(
                    destination.url, json=envelope, headers=request_headers
                )
                if response.status_code >= 300:
                    message = (
                        f"Webhook {destination.url} failed with status {response.status_code}"
                    )
                    failures.append(message)
                    logger.warning(
                        "webhook.failed",
                        extra={
                            "event_type": event_type,
                            "tenant_id": tenant_id,
                            "status": response.status_code,
                            "url": destination.url,
                        },
                    )
        if failures:
            raise WebhookDispatchError("; ".join(failures))


@dataclass(slots=True)
class WebhookDestination:
    url: str
    headers: dict[str, str]


class _null_async_context:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client

    async def __aenter__(self) -> httpx.AsyncClient:
        return self.client

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None
