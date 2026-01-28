from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx

from app.core.config import Settings, get_settings
from app.core.tracing import get_trace_id

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


@dataclass(slots=True)
class WebhookDispatcher:
    """Dispatch webhook events to configured endpoints."""

    settings: Settings
    client: httpx.AsyncClient | None = None

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.client = client

    def resolve_destinations(self, event_type: str) -> list[str]:
        return self._resolve_urls(event_type)

    def _resolve_urls(self, event_type: str) -> list[str]:
        if event_type == "DocumentCreated":
            return list(
                self.settings.webhook_document_created_urls
                or self.settings.webhook_document_generated_urls
            )
        if event_type == "DocumentSigned":
            return list(
                self.settings.webhook_document_signed_urls
                or self.settings.webhook_signed_urls
            )
        if event_type == "DocumentExported":
            return list(
                self.settings.webhook_document_exported_urls
                or self.settings.webhook_exported_urls
            )
        if event_type == "RiskAssessed":
            return list(self.settings.webhook_risk_assessed_urls)
        if event_type == "PPEIssued":
            return list(self.settings.webhook_ppe_issued_urls)
        if event_type == "PPEReturned":
            return list(self.settings.webhook_ppe_returned_urls)
        if event_type == "TrainingCompleted":
            return list(self.settings.webhook_training_completed_urls)
        if event_type == "TrainingAssigned":
            return list(self.settings.webhook_training_assigned_urls)
        return []

    async def dispatch(
        self,
        *,
        event_type: str,
        tenant_id: str,
        payload: dict[str, Any],
        destination: str,
        headers: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> None:
        trace_id = get_trace_id()
        envelope = {
            "event_type": event_type,
            "tenant_id": tenant_id,
            "sent_at": datetime.now(tz=timezone.utc).isoformat(),
            "payload": payload,
        }
        request_headers: dict[str, str] = {"X-Correlation-ID": trace_id}
        if headers:
            for key, value in headers.items():
                request_headers[str(key)] = str(value)
        event_id = payload.get("event_id")
        if event_id:
            request_headers.setdefault("Idempotency-Key", str(event_id))
        if idempotency_key:
            request_headers["Idempotency-Key"] = str(idempotency_key)

        async with httpx.AsyncClient(
            timeout=self.settings.webhook_timeout_seconds
        ) if self.client is None else _null_async_context(self.client) as client:
            response = await client.post(destination, json=envelope, headers=request_headers)
            if response.status_code >= 300:
                message = f"Webhook {destination} failed with status {response.status_code}"
                logger.warning(
                    "webhook.failed",
                    extra={
                        "event_type": event_type,
                        "tenant_id": tenant_id,
                        "status": response.status_code,
                        "url": destination,
                    },
                )
                raise WebhookDispatchError(message, status_code=response.status_code)


class _null_async_context:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client

    async def __aenter__(self) -> httpx.AsyncClient:
        return self.client

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None
