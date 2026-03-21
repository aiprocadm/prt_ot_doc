"""Notifications application module."""

from .schemas import (
    CalendarEventRead,
    ChannelSettingsIn,
    ChannelSettingsOut,
    MarkReadRequest,
    NotificationPage,
    NotificationRead,
    NotificationTemplateIn,
    NotificationTemplateOut,
)
from .service import NotificationApplicationService

__all__ = [
    "CalendarEventRead",
    "ChannelSettingsIn",
    "ChannelSettingsOut",
    "MarkReadRequest",
    "NotificationApplicationService",
    "NotificationPage",
    "NotificationRead",
    "NotificationTemplateIn",
    "NotificationTemplateOut",
]
