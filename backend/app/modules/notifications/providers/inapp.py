"""In-app notification provider (RC-011).

In-app notifications are delivered by virtue of being persisted and shown in the app's
notification list, so delivery always succeeds. This is the terminal link of the
channel-fallback escalation chain.
"""

from __future__ import annotations

from app.models.notifications import Notification, NotificationChannel
from app.modules.notifications.providers.base import (
    DeliveryResult,
    NotificationContact,
)


class InAppProvider:
    channel = NotificationChannel.INAPP

    async def deliver(
        self, *, notification: Notification, contact: NotificationContact
    ) -> DeliveryResult:
        return DeliveryResult.ok()
