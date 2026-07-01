"""SMTP email notification provider (RC-011).

Thin real client: sends via stdlib ``smtplib`` off the event loop. Gated by
``NOTIFICATIONS_DELIVERY_ENABLED`` + ``SMTP_HOST``; unconfigured or missing recipient
address yields ``SKIPPED`` (not a false ``SENT``).
"""

from __future__ import annotations

import asyncio

from app.models.notifications import Notification, NotificationChannel
from app.modules.notifications.providers.base import (
    DeliveryResult,
    NotificationContact,
)


class EmailProvider:
    channel = NotificationChannel.EMAIL

    def __init__(self, settings) -> None:
        self._settings = settings

    async def deliver(
        self, *, notification: Notification, contact: NotificationContact
    ) -> DeliveryResult:
        s = self._settings
        if (
            not getattr(s, "notifications_delivery_enabled", False)
            or not (s.smtp_host or "").strip()
        ):
            return DeliveryResult.skip("email delivery disabled or SMTP not configured")
        to_addr = (contact.email or "").strip()
        if not to_addr:
            return DeliveryResult.skip("recipient has no email address")
        try:
            await asyncio.to_thread(self._send, to_addr, notification)
        except Exception as exc:  # pragma: no cover - network/SMTP failure path
            return DeliveryResult.fail(f"smtp: {exc}")
        return DeliveryResult.ok()

    def _send(self, to_addr: str, notification: Notification) -> None:
        import smtplib
        from email.message import EmailMessage

        s = self._settings
        msg = EmailMessage()
        msg["Subject"] = notification.title
        msg["From"] = (s.smtp_from or s.admin_email or "no-reply@localhost").strip()
        msg["To"] = to_addr
        msg.set_content(notification.body)
        with smtplib.SMTP(s.smtp_host, int(s.smtp_port), timeout=10) as server:
            if getattr(s, "smtp_use_tls", True):
                server.starttls()
            if (s.smtp_username or "").strip():
                server.login(s.smtp_username, s.smtp_password)
            server.send_message(msg)
