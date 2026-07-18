"""Field-ops ORM models (compliance deadlines, calendar, offline sync, permits) — extracted from models.py (ARCH-2 decomposition).

Pure move of class definitions: same registry, identical tables. Public import
paths ``from app.models.models import X`` / ``from app.models import X`` are
preserved by re-exports in models.py / __init__.py. External classes referenced
only in ``Mapped[...]`` annotations are resolved by SQLAlchemy's class registry
(TYPE_CHECKING import only; no runtime import cycle back into models.py).
"""

from __future__ import annotations

import enum
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import (
    TenantBaseModel,
)

if TYPE_CHECKING:  # pragma: no cover - type-checker only; SA resolves via registry
    from app.models.models import (
        Person,
        Position,
    )


class ComplianceDeadline(TenantBaseModel):
    __tablename__ = "compliance_deadlines"

    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False)
    person_id: Mapped[str | None] = mapped_column(
        ForeignKey("person.id", ondelete="SET NULL"), nullable=True, index=True
    )
    site_id: Mapped[str | None] = mapped_column(
        ForeignKey("site.id", ondelete="SET NULL"), nullable=True
    )
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="upcoming")
    reminder_policy: Mapped[str | None] = mapped_column(Text, nullable=True)


class CalendarEvent(TenantBaseModel):
    __tablename__ = "calendar_events"

    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_id: Mapped[str] = mapped_column(String(36), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    site_id: Mapped[str | None] = mapped_column(
        ForeignKey("site.id", ondelete="SET NULL"), nullable=True
    )
    assigned_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")


class OfflineSyncBatch(TenantBaseModel):
    __tablename__ = "offline_sync_batches"

    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    device_id: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )
    error_payload: Mapped[dict[str, Any] | None] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=True
    )


class OfflineMediaQueue(TenantBaseModel):
    __tablename__ = "offline_media_queue"

    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    device_id: Mapped[str] = mapped_column(String(128), nullable=False)
    local_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    file_id: Mapped[str | None] = mapped_column(
        ForeignKey("file.id", ondelete="SET NULL"), nullable=True
    )
    upload_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=True
    )


class ExternalRegistryJob(TenantBaseModel):
    __tablename__ = "external_registry_jobs"

    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False)
    registry_type: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    request_payload: Mapped[dict[str, Any] | None] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=True
    )
    response_payload: Mapped[dict[str, Any] | None] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=True
    )


class PermitStatus(str, enum.Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"


class Permit(TenantBaseModel):
    person_id: Mapped[str] = mapped_column(ForeignKey("person.id"), nullable=False, index=True)
    position_id: Mapped[str | None] = mapped_column(
        ForeignKey("position.id", ondelete="SET NULL"), nullable=True, index=True
    )
    permit_type: Mapped[str] = mapped_column(String(128), nullable=False)
    issued_at: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)
    valid_until: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=PermitStatus.ACTIVE.value
    )

    position: Mapped[Position | None] = relationship(backref="permits")
    person: Mapped[Person] = relationship(backref="permits")

    __table_args__ = (Index("ix_permit_position", "tenant_id", "position_id"),)
