"""SMTP email notification provider (RC-011).

Thin real client: sends via stdlib ``smtplib`` off the event loop. Gated by
``NOTIFICATIONS_DELIVERY_ENABLED`` + ``SMTP_HOST``; unconfigured or missing recipient
address yields ``SKIPPED`` (not a false ``SENT``).

BIZ-52 срез-10 (Доп. №1 разд. 52.2): письмо подписывается брендом арендатора —
именем отправителя, `Reply-To` на почту поддержки партнёра и подписью в теле.
Адрес отправителя остаётся платформенным: он держит SPF и DKIM.
"""

from __future__ import annotations

import asyncio

from app.domains.reseller.mail_identity import (
    MailIdentity,
    apply_signature,
    build_mail_identity,
)
from app.domains.reseller.white_label import PLATFORM_BRAND
from app.models.notifications import Notification, NotificationChannel
from app.modules.notifications.providers.base import (
    DeliveryResult,
    NotificationContact,
)
from app.services.app_branding import brand_for_tenant_id


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
        identity = await self._identity(notification)
        try:
            await asyncio.to_thread(self._send, to_addr, notification, identity)
        except Exception as exc:  # pragma: no cover - network/SMTP failure path
            return DeliveryResult.fail(f"smtp: {exc}")
        return DeliveryResult.ok()

    async def _identity(self, notification: Notification) -> MailIdentity:
        """Бренд, которым подписать письмо (BIZ-52 срез-10, разд. 52.2).

        Один запрос на письмо: рядом с открытием SMTP-соединения он не заметен, а
        кэш пришлось бы сбрасывать при каждой правке бренда — и однажды он
        подписал бы письмо именем, которое партнёр уже сменил.

        Сбой чтения бренда НЕ роняет отправку: письмо без партнёрского имени
        хуже, чем с ним, но недоставленное письмо хуже обоих.
        """

        try:
            brand = await brand_for_tenant_id(str(notification.tenant_id))
        except Exception:  # pragma: no cover - деградация, а не отказ доставки
            brand = PLATFORM_BRAND
        return build_mail_identity(brand)

    def _send(self, to_addr: str, notification: Notification, identity: MailIdentity) -> None:
        import smtplib
        from email.headerregistry import Address
        from email.message import EmailMessage

        s = self._settings
        msg = EmailMessage()
        msg["Subject"] = notification.title
        from_addr = (s.smtp_from or s.admin_email or "no-reply@localhost").strip()
        # Адрес остаётся платформенным (SPF/DKIM), подменяется только видимое имя.
        # `Address` кодирует кириллицу по RFC 2047 сам — собранная руками строка
        # `"Имя" <адрес>` ушла бы в письмо байтами и показалась крякозябрами.
        msg["From"] = self._from_header(identity.display_name, from_addr, Address)
        if identity.reply_to:
            msg["Reply-To"] = identity.reply_to
        msg["To"] = to_addr
        msg.set_content(apply_signature(notification.body, identity.signature))
        with smtplib.SMTP(s.smtp_host, int(s.smtp_port), timeout=10) as server:
            if getattr(s, "smtp_use_tls", True):
                server.starttls()
            if (s.smtp_username or "").strip():
                server.login(s.smtp_username, s.smtp_password)
            server.send_message(msg)

    @staticmethod
    def _from_header(display_name: str, from_addr: str, address_cls):
        """Собрать `From`. Без имени — прежний голый адрес."""

        if not display_name:
            return from_addr
        local, _, domain = from_addr.rpartition("@")
        if not local or not domain:
            return from_addr
        return address_cls(display_name=display_name, username=local, domain=domain)
