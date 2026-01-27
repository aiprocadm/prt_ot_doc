from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

from app.core.config import Settings, get_settings
from app.core.tracing import get_trace_id

logger = logging.getLogger(__name__)


class WebhookDispatchError(RuntimeError):
    """Raised when a webhook cannot be delivered successfully."""


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

    def _resolve_urls(self, event_type: str) -> list[str]:
        if event_type == "DocumentGenerated":
            return list(self.settings.webhook_document_generated_urls)
        if event_type == "Signed":
            return list(self.settings.webhook_signed_urls)
        if event_type == "Exported":
            return list(self.settings.webhook_exported_urls)
        if event_type == "RiskAssessed":
            return list(self.settings.webhook_risk_assessed_urls)
        if event_type == "PPEIssued":
            return list(self.settings.webhook_ppe_issued_urls)
        if event_type == "TrainingCompleted":
            return list(self.settings.webhook_training_completed_urls)
        return []

    async def dispatch(
        self,
        *,
        event_type: str,
        tenant_id: str,
        payload: dict,
    ) -> None:
        urls = self._resolve_urls(event_type)
        if not urls:
            logger.debug(
                "webhook.skip",
                extra={"event_type": event_type, "tenant_id": tenant_id},
            )
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

        async with httpx.AsyncClient(
            timeout=self.settings.webhook_timeout_seconds
        ) if self.client is None else _null_async_context(self.client) as client:
            for url in urls:
                response = await client.post(url, json=envelope, headers=headers)
                if response.status_code >= 300:
                    message = f"Webhook {url} failed with status {response.status_code}"
                    logger.warning(
                        "webhook.failed",
                        extra={
                            "event_type": event_type,
                            "tenant_id": tenant_id,
                            "status": response.status_code,
                            "url": url,
                        },
                    )
                    raise WebhookDispatchError(message)


class _null_async_context:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client

    async def __aenter__(self) -> httpx.AsyncClient:
        return self.client

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None
