from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class NotificationRead(BaseModel):
    id: str
    channel: str
    type: str
    title: str
    body: str
    payload: dict[str, object] | None = None
    priority: str
    status: str
    is_read: bool
    deeplink: str | None = None
    scheduled_at: datetime
    sent_at: datetime | None = None


class NotificationPage(BaseModel):
    items: list[NotificationRead]
    next_cursor: str | None = None
    unread_count: int = 0


class MarkReadRequest(BaseModel):
    ids: list[str] = Field(default_factory=list)
    model_config = ConfigDict(extra="forbid")


class ChannelSettingsIn(BaseModel):
    email_enabled: bool = True
    telegram_enabled: bool = False
    inapp_enabled: bool = True
    email: str | None = None
    telegram_chat_id: str | None = None
    quiet_hours: dict[str, str] | None = None
    digest_mode: str | None = None
    channel_preferences: dict[str, object] | None = None


class ChannelSettingsOut(ChannelSettingsIn):
    user_id: str


class NotificationTemplateIn(BaseModel):
    code: str
    channel: str
    type: str
    locale: str = "ru"
    subject_template: str | None = None
    title_template: str | None = None
    body_template: str
    is_active: bool = True
    variables_schema: dict[str, object] | None = None
    model_config = ConfigDict(extra="forbid")


class NotificationTemplateOut(NotificationTemplateIn):
    id: str


class CalendarEventRead(BaseModel):
    id: str
    source: str
    entity_type: str
    entity_id: str
    title: str
    date: datetime
    status: str | None = None
    deeplink: str | None = None
