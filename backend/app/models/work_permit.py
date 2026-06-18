"""Work-permit (наряд-допуск) models: document + brigade members + event log."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TenantBaseModel


class WorkPermit(TenantBaseModel):
    __tablename__ = "work_permit"

    number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    work_type: Mapped[str] = mapped_column(String(32), nullable=False)
    zone_text: Mapped[str] = mapped_column(String(255), nullable=False)
    site_id: Mapped[str | None] = mapped_column(
        ForeignKey("site.id", ondelete="SET NULL"), nullable=True, index=True
    )
    equipment_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    hazards_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    measures_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    # секции официальной формы 782н (Ф1)
    subdivision_text: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    conditions_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    safety_systems: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    measures_before_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    measures_during_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    special_conditions_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    ppe_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    planned_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    planned_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    suspended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("tenant_id", "number", name="uq_work_permit_tenant_number"),
        Index("ix_work_permit_status", "tenant_id", "status"),
    )


class WorkPermitMember(TenantBaseModel):
    __tablename__ = "work_permit_member"

    work_permit_id: Mapped[str] = mapped_column(
        ForeignKey("work_permit.id", ondelete="CASCADE"), nullable=False, index=True
    )
    person_id: Mapped[str] = mapped_column(
        ForeignKey("person.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "work_permit_id", "person_id", "role",
            name="uq_work_permit_member",
        ),
    )


class WorkPermitEvent(TenantBaseModel):
    __tablename__ = "work_permit_event"

    work_permit_id: Mapped[str] = mapped_column(
        ForeignKey("work_permit.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    actor_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    photo_file_id: Mapped[str | None] = mapped_column(
        ForeignKey("file.id", ondelete="SET NULL"), nullable=True
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
