"""Notification delivery providers (RC-011)."""

from __future__ import annotations

from app.modules.notifications.providers.base import (
    DeliveryOutcome,
    DeliveryResult,
    NotificationContact,
    NotificationProvider,
)
from app.modules.notifications.providers.email import EmailProvider
from app.modules.notifications.providers.inapp import InAppProvider
from app.modules.notifications.providers.telegram import TelegramProvider
from app.modules.notifications.providers.webhook import WebhookProvider

__all__ = [
    "DeliveryOutcome",
    "DeliveryResult",
    "NotificationContact",
    "NotificationProvider",
    "EmailProvider",
    "InAppProvider",
    "TelegramProvider",
    "WebhookProvider",
]
