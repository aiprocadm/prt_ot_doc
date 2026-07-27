from __future__ import annotations

import hmac
import json
import logging
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from time import time
from typing import Any, cast
from urllib.parse import urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.metrics import Metrics, get_metrics
from app.core.secret_cipher import decrypt_secret
from app.core.ssrf_guard import UnsafeWebhookURLError, assert_safe_webhook_url
from app.core.tracing import get_trace_id
from app.models.models import WebhookEndpoint, WebhookSubscription

logger = logging.getLogger(__name__)


class WebhookDispatchError(RuntimeError):
    """Raised when a webhook cannot be delivered successfully."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code

    @property
    def error_class(self) -> str:
        if self.status_code is None:
            return "unknown"
        if self.status_code >= 500:
            return "http_5xx"
        if self.status_code == 408:
            return "http_408"
        if self.status_code == 429:
            return "http_429"
        return "http_4xx"


@dataclass(slots=True, init=False)
class WebhookDispatcher:
    """Dispatch webhook events to configured endpoints."""

    settings: Settings
    metrics: Metrics
    client: httpx.AsyncClient | None = None

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.client = client
        self.metrics = get_metrics()

    def resolve_destinations(self, event_type: str) -> list[str]:
        return self._resolve_urls(event_type)

    async def resolve_destinations_for_tenant(
        self,
        *,
        event_type: str,
        tenant_id: str,
        session: AsyncSession,
    ) -> list[str]:
        destinations = await self.resolve_destinations_with_headers(
            event_type=event_type,
            tenant_id=tenant_id,
            session=session,
        )
        return [destination.url for destination in destinations]

    async def resolve_destinations_with_headers(
        self,
        *,
        event_type: str,
        tenant_id: str,
        session: AsyncSession,
    ) -> list[WebhookDestination]:
        return await self._resolve_destinations(
            event_type=event_type,
            tenant_id=tenant_id,
            session=session,
        )

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
                self.settings.webhook_document_signed_urls or self.settings.webhook_signed_urls
            ),
            "DocumentExported": (
                self.settings.webhook_document_exported_urls or self.settings.webhook_exported_urls
            ),
            "RiskAssessed": self.settings.webhook_risk_assessed_urls,
            "PPEIssued": self.settings.webhook_ppe_issued_urls,
            "PPEReturned": self.settings.webhook_ppe_returned_urls,
            "TrainingCompleted": self.settings.webhook_training_completed_urls,
            "TrainingAssigned": self.settings.webhook_training_assigned_urls,
        }
        return list(urls_by_event.get(event_type, ()))

    @staticmethod
    def _event_aliases(event_type: str) -> set[str]:
        aliases: dict[str, set[str]] = {
            "Signed": {"Signed", "DocumentSigned"},
            "DocumentSigned": {"Signed", "DocumentSigned"},
            "Exported": {"Exported", "DocumentExported"},
            "DocumentExported": {"Exported", "DocumentExported"},
        }
        return aliases.get(event_type, {event_type})

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
    ) -> list[WebhookDestination]:
        event_variants = self._event_aliases(event_type)

        subscription_base = select(WebhookSubscription).where(
            WebhookSubscription.enabled.is_(True),
            WebhookSubscription.event_type.in_(event_variants),
        )
        tenant_subs = (
            (
                await session.execute(
                    subscription_base.where(WebhookSubscription.tenant_id == tenant_id).order_by(
                        WebhookSubscription.created_at.asc()
                    )
                )
            )
            .scalars()
            .all()
        )
        if tenant_subs:
            destinations: list[WebhookDestination] = []
            for sub in tenant_subs:
                if not self._validate_url(sub.url):
                    logger.warning(
                        "webhook.invalid_url", extra={"event_type": event_type, "url": sub.url}
                    )
                    continue
                destinations.append(
                    WebhookDestination(
                        url=sub.url,
                        headers={
                            str(key): str(value) for key, value in (sub.headers or {}).items()
                        },
                        secret=decrypt_secret(sub.secret),  # SEC-67: decrypt at use
                    )
                )
            return destinations

        # Legacy fallback to cross-tenant subscriptions. Unreachable on PostgreSQL since
        # SEC-65 armed webhook_subscription: tenant_id IS NULL never satisfies the
        # tenant_isolation predicate, so such rows are invisible — and the migration
        # refuses to run while any exist. Kept for SQLite/dev parity; the only writer of
        # global rows in the repository is tests/test_webhook_routing.py.
        global_subs = (
            (
                await session.execute(
                    subscription_base.where(WebhookSubscription.tenant_id.is_(None)).order_by(
                        WebhookSubscription.created_at.asc()
                    )
                )
            )
            .scalars()
            .all()
        )
        if global_subs:
            destinations = []  # list[WebhookDestination]
            for sub in global_subs:
                if not self._validate_url(sub.url):
                    logger.warning(
                        "webhook.invalid_url", extra={"event_type": event_type, "url": sub.url}
                    )
                    continue
                destinations.append(
                    WebhookDestination(
                        url=sub.url,
                        headers={
                            str(key): str(value) for key, value in (sub.headers or {}).items()
                        },
                        secret=decrypt_secret(sub.secret),  # SEC-67: decrypt at use
                    )
                )
            return destinations

        # Backward compatibility for legacy endpoint table.
        base_stmt = select(WebhookEndpoint).where(WebhookEndpoint.is_enabled.is_(True))
        tenant_stmt = base_stmt.where(WebhookEndpoint.tenant_id == tenant_id).order_by(
            WebhookEndpoint.created_at.asc()
        )
        tenant_result = await session.execute(tenant_stmt)
        tenant_rows = tenant_result.scalars().all()
        if tenant_rows:
            return self._build_destinations_from_rows(
                event_type=event_type,
                rows=[
                    row
                    for row in tenant_rows
                    if (not row.subscribed_events)
                    or bool(event_variants.intersection(set(row.subscribed_events or [])))
                ],
            )

        global_stmt = base_stmt.where(WebhookEndpoint.tenant_id.is_(None)).order_by(
            WebhookEndpoint.created_at.asc()
        )
        global_result = await session.execute(global_stmt)
        return self._build_destinations_from_rows(
            event_type=event_type,
            rows=[
                row
                for row in global_result.scalars().all()
                if (not row.subscribed_events)
                or bool(event_variants.intersection(set(row.subscribed_events or [])))
            ],
        )

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
        rows: Iterable[WebhookEndpoint],
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
                    endpoint_id=row.id,
                    secret=decrypt_secret(row.secret),  # SEC-67: decrypt at use
                    timeout_ms=row.timeout_ms,
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
                return rows
        return self._build_destinations_from_urls(
            event_type=event_type,
            urls=self._resolve_urls(event_type),
        )

    async def dispatch(
        self,
        *,
        event_type: str,
        tenant_id: str,
        payload: dict[str, Any],
        destination: str | None = None,
        headers: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
        session: AsyncSession | None = None,
    ) -> None:
        if destination:
            destinations = [WebhookDestination(url=destination, headers={})]
        else:
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

        payload_correlation = str(payload.get("correlation_id") or "").strip()
        trace_id = payload_correlation or get_trace_id()
        event_id = str(payload.get("event_id") or payload.get("id") or "")
        envelope = {
            "id": event_id,
            "type": event_type,
            "event_type": event_type,
            "occurred_at": datetime.now(tz=timezone.utc).isoformat(),
            "correlation_id": trace_id,
            "payload": payload,
        }
        timestamp_ms = str(int(time() * 1000))
        request_headers: dict[str, str] = {
            "X-Correlation-Id": trace_id,
            "X-Event-Type": event_type,
            "X-Tenant": tenant_id,
            "X-Timestamp": timestamp_ms,
        }
        if headers:
            for key, value in headers.items():
                request_headers[str(key)] = str(value)
        if event_id:
            request_headers.setdefault("X-Event-Id", str(event_id))
            request_headers.setdefault("Idempotency-Key", str(event_id))
        if idempotency_key:
            request_headers["Idempotency-Key"] = str(idempotency_key)

        failures: list[tuple[str, int]] = []
        _client_ctx: httpx.AsyncClient | _null_async_context = (
            httpx.AsyncClient(timeout=self.settings.webhook_timeout_seconds)
            if self.client is None
            else _null_async_context(self.client)
        )
        async with _client_ctx as _acm_client:
            client = cast(httpx.AsyncClient, _acm_client)
            for dest in destinations:
                merged_headers = {**request_headers, **dest.headers}
                body = json.dumps(envelope, separators=(",", ":")).encode("utf-8")
                if dest.secret:
                    sign_payload = f"{timestamp_ms}.".encode("utf-8") + body
                    signature = hmac.new(
                        dest.secret.encode("utf-8"), sign_payload, sha256
                    ).hexdigest()
                    merged_headers["X-Signature"] = f"v1={signature}"
                if self.settings.webhook_ssrf_guard_enabled:
                    try:
                        await assert_safe_webhook_url(dest.url, app_env=self.settings.app_env)
                    except UnsafeWebhookURLError as exc:
                        # SEC-64 §64.3: block SSRF targets before any network call.
                        # Sentinel status 0 = "blocked pre-flight" (distinct from HTTP codes).
                        failures.append((dest.url, 0))
                        logger.warning(
                            "webhook.blocked_ssrf",
                            extra={
                                "event_type": event_type,
                                "tenant_id": tenant_id,
                                "url": dest.url,
                                "reason": str(exc),
                            },
                        )
                        continue
                response = await client.post(
                    dest.url,
                    content=body,
                    headers={**merged_headers, "content-type": "application/json"},
                    timeout=max((dest.timeout_ms or 5000) / 1000, 0.1),
                )
                if response.status_code >= 300:
                    failures.append((dest.url, response.status_code))
                    logger.warning(
                        "webhook.failed",
                        extra={
                            "event_type": event_type,
                            "tenant_id": tenant_id,
                            "status": response.status_code,
                            "url": dest.url,
                        },
                    )
                    continue
                self.metrics.record_outbox_routed(event_type=event_type, destination=dest.url)

        if failures:
            message = "; ".join(
                f"Webhook {url} failed with status {status}" for url, status in failures
            )
            raise WebhookDispatchError(message, status_code=failures[0][1])


@dataclass(slots=True)
class WebhookDestination:
    url: str
    headers: dict[str, str]
    endpoint_id: str | None = None
    secret: str | None = None
    timeout_ms: int = 5000


class _null_async_context:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client

    async def __aenter__(self) -> httpx.AsyncClient:
        return self.client

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None
