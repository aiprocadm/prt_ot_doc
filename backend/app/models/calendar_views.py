"""Saved Smart Calendar view models (vNext-CAL-01 / Phase 4.1).

A `SavedCalendarView` is a per-user, per-tenant named snapshot of the
Smart Calendar filter state — sources, person/site, plan-fact toggle, SLA
toggle + bands, resource-load toggle + dimension. Stored as JSON payload
so future toggles can be added without further migrations.

Uniqueness is `(tenant_id, user_id, name)`: each user may have many
views, but names are unique per user (case-sensitive match — the UI
deduplicates by exact name).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import SoftDeleteMixin, TenantBaseModel

__all__ = ["SavedCalendarView"]


class SavedCalendarView(TenantBaseModel, SoftDeleteMixin):
    """User-defined Smart Calendar filter preset.

    The `payload` JSON holds the wire shape of the calendar query state
    (see `app.schemas.calendar_views.SavedCalendarViewPayload`); we store
    it opaquely so the model does not need a migration each time the UI
    adds a new toggle.
    """

    __tablename__ = "saved_calendar_views"

    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", "name", name="uq_saved_calendar_views_name"),
        Index("ix_saved_calendar_views_user", "tenant_id", "user_id"),
    )
