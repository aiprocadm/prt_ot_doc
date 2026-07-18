"""Notification delivery provider contract (RC-011).

A ``NotificationProvider`` turns a stored :class:`Notification` into an actual delivery
attempt on one channel and reports an honest :class:`DeliveryResult`. Real external
delivery is feature-flagged (``NOTIFICATIONS_DELIVERY_ENABLED``) and per-channel
configured; when off/unconfigured a provider returns ``SKIPPED`` rather than pretending
to have sent (which was the RC-011 stub defect: ``status=SENT`` with no call).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from app.models.notifications import Notification, NotificationChannel


class DeliveryOutcome(str, Enum):
    DELIVERED = "delivered"
    FAILED = "failed"
    SKIPPED = "skipped"  # provider disabled / unconfigured / no recipient contact


@dataclass(frozen=True)
class NotificationContact:
    """Recipient addressing resolved from ``NotificationChannelSettings`` / ``User``."""

    email: str | None = None
    telegram_chat_id: str | None = None


@dataclass(frozen=True)
class DeliveryResult:
    outcome: DeliveryOutcome
    detail: str | None = None
    provider_ref: str | None = None

    @property
    def delivered(self) -> bool:
        return self.outcome is DeliveryOutcome.DELIVERED

    @property
    def failed(self) -> bool:
        return self.outcome is DeliveryOutcome.FAILED

    @property
    def skipped(self) -> bool:
        return self.outcome is DeliveryOutcome.SKIPPED

    @classmethod
    def ok(cls, provider_ref: str | None = None) -> "DeliveryResult":
        return cls(DeliveryOutcome.DELIVERED, provider_ref=provider_ref)

    @classmethod
    def fail(cls, detail: str) -> "DeliveryResult":
        return cls(DeliveryOutcome.FAILED, detail=detail[:255])

    @classmethod
    def skip(cls, detail: str) -> "DeliveryResult":
        return cls(DeliveryOutcome.SKIPPED, detail=detail[:255])


class NotificationProvider(Protocol):
    channel: NotificationChannel

    async def deliver(
        self, *, notification: Notification, contact: NotificationContact
    ) -> DeliveryResult: ...
