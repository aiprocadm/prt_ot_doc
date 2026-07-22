"""Webhook notification provider (RC-011).

Thin real client: HTTP POSTs the notification to ``WEBHOOK_NOTIFICATION_URL`` with an
optional HMAC-SHA256 signature (reusing ``INBOUND_WEBHOOK_HMAC_SECRET``). Gated by
``NOTIFICATIONS_DELIVERY_ENABLED`` + a configured URL; otherwise ``SKIPPED``.
"""

from __future__ import annotations

import hashlib
import hmac
import json

from app.models.notifications import Notification, NotificationChannel
from app.modules.notifications.providers.base import (
    DeliveryResult,
    NotificationContact,
)


class WebhookProvider:
    channel = NotificationChannel.WEBHOOK

    def __init__(self, settings) -> None:
        self._settings = settings

    async def deliver(
        self, *, notification: Notification, contact: NotificationContact
    ) -> DeliveryResult:
        s = self._settings
        url = (getattr(s, "webhook_notification_url", None) or "").strip()
        if not getattr(s, "notifications_delivery_enabled", False) or not url:
            return DeliveryResult.skip("webhook delivery disabled or URL not configured")

        # SEC-64 §64.3: block SSRF targets before the outbound call.
        if getattr(s, "webhook_ssrf_guard_enabled", True):
            from app.core.ssrf_guard import (
                UnsafeWebhookURLError,
                assert_safe_webhook_url,
            )

            try:
                await assert_safe_webhook_url(url, app_env=getattr(s, "app_env", "production"))
            except UnsafeWebhookURLError as exc:
                return DeliveryResult.fail(f"webhook blocked (ssrf): {exc}")

        import httpx

        body = json.dumps(
            {
                "id": notification.id,
                "tenant_id": str(notification.tenant_id),
                "user_id": notification.user_id,
                "type": notification.type.value,
                "title": notification.title,
                "body": notification.body,
                "priority": notification.priority.value,
                "payload": notification.payload,
            },
            ensure_ascii=False,
            default=str,
        ).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        secret = (getattr(s, "inbound_webhook_hmac_secret", "") or "").strip()
        if secret:
            headers["X-Signature"] = hmac.new(
                secret.encode("utf-8"), body, hashlib.sha256
            ).hexdigest()
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, content=body, headers=headers)
            if resp.status_code >= 400:
                return DeliveryResult.fail(f"webhook http {resp.status_code}")
        except Exception as exc:  # pragma: no cover - network failure path
            return DeliveryResult.fail(f"webhook: {exc}")
        return DeliveryResult.ok()
