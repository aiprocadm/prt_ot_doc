"""Telegram notification provider (RC-011).

Thin real client: posts to the Bot API ``sendMessage``. Gated by
``NOTIFICATIONS_DELIVERY_ENABLED`` + ``TELEGRAM_BOT_TOKEN``; unconfigured or missing
``telegram_chat_id`` yields ``SKIPPED``.
"""

from __future__ import annotations

from app.models.notifications import Notification, NotificationChannel
from app.modules.notifications.providers.base import (
    DeliveryResult,
    NotificationContact,
)


class TelegramProvider:
    channel = NotificationChannel.TELEGRAM

    def __init__(self, settings) -> None:
        self._settings = settings

    async def deliver(
        self, *, notification: Notification, contact: NotificationContact
    ) -> DeliveryResult:
        s = self._settings
        token = (getattr(s, "telegram_bot_token", "") or "").strip()
        if not getattr(s, "notifications_delivery_enabled", False) or not token:
            return DeliveryResult.skip("telegram delivery disabled or bot token not configured")
        chat_id = (contact.telegram_chat_id or "").strip()
        if not chat_id:
            return DeliveryResult.skip("recipient has no telegram_chat_id")

        import httpx

        text = f"{notification.title}\n\n{notification.body}"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json={"chat_id": chat_id, "text": text},
                )
            if resp.status_code >= 400:
                return DeliveryResult.fail(f"telegram http {resp.status_code}")
        except Exception as exc:  # pragma: no cover - network failure path
            return DeliveryResult.fail(f"telegram: {exc}")
        return DeliveryResult.ok()
