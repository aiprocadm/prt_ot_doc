"""ORM models for safety checklist inspections and corrective actions."""

from __future__ import annotations

import enum
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.models.base import TenantBaseModel

if TYPE_CHECKING:  # pragma: no cover - type checking only
    pass

__all__ = [
    "Checklist",
    "Inspection",
    "InspectionStatus",
    "Violation",
    "ViolationSeverity",
    "CorrectiveAction",
    "CorrectiveActionStatus",
]


class Checklist(TenantBaseModel):
    """Tenant-scoped checklist describing inspection requirements."""

    npa_code: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    inspections = relationship(
        "Inspection",
        back_populates="checklist",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "npa_code",
            "version",
            name="uq_checklist_tenant_code_version",
        ),
        Index("ix_checklist_npa_code", "tenant_id", "npa_code"),
        Index("ix_checklist_title", "tenant_id", "title"),
        Index("ix_checklist_created_at", "created_at"),
    )


class InspectionStatus(str, enum.Enum):
    """Lifecycle states of a checklist inspection."""

    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class Inspection(TenantBaseModel):
    """Execution of a checklist at a specific site."""

    site_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("site.id", ondelete="RESTRICT"),
        nullable=False,
    )
    checklist_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("checklist.id", ondelete="RESTRICT"),
        nullable=False,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[InspectionStatus] = mapped_column(
        Enum(InspectionStatus, name="inspectionstatus"),
        nullable=False,
        default=InspectionStatus.PLANNED,
    )

    checklist = relationship("Checklist", back_populates="inspections")
    site = relationship("Site", backref="inspections")
    violations = relationship(
        "Violation",
        back_populates="inspection",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        Index("ix_inspection_site_id", "site_id"),
        Index("ix_inspection_checklist_id", "checklist_id"),
        Index("ix_inspection_status", "status"),
        Index("ix_inspection_started_at", "started_at"),
    )


class ViolationSeverity(str, enum.Enum):
    """Severity scale for checklist violations."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Violation(TenantBaseModel):
    """Inspection finding describing a violated checklist clause."""

    inspection_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("inspection.id", ondelete="CASCADE"),
        nullable=False,
    )
    clause_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    severity: Mapped[ViolationSeverity] = mapped_column(
        Enum(ViolationSeverity, name="violationseverity"), nullable=False
    )
    photo_key: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)

    inspection = relationship("Inspection", back_populates="violations")
    corrective_actions = relationship(
        "CorrectiveAction",
        back_populates="violation",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        Index("ix_violation_inspection_id", "inspection_id"),
        Index("ix_violation_severity", "severity"),
    )


class CorrectiveActionStatus(str, enum.Enum):
    """State of remediation for a violation."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    OVERDUE = "overdue"


class CorrectiveAction(TenantBaseModel):
    """Action required to resolve a violation."""

    violation_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("violation.id", ondelete="CASCADE"),
        nullable=False,
    )
    action: Mapped[str] = mapped_column(Text, nullable=False)
    due_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[CorrectiveActionStatus] = mapped_column(
        Enum(CorrectiveActionStatus, name="correctiveactionstatus"),
        nullable=False,
        default=CorrectiveActionStatus.PENDING,
    )

    violation = relationship("Violation", back_populates="corrective_actions")

    __table_args__ = (
        Index("ix_corrective_action_violation_id", "violation_id"),
        Index("ix_corrective_action_status", "status"),
        Index("ix_corrective_action_due_date", "due_date"),
    )

    @validates("due_date")
    def _validate_due_date(self, key: str, value: date | None) -> date | None:
        if value is not None and value < date.today():
            raise ValueError("due_date cannot be in the past")
        return value
