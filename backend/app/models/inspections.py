"""Inspection / attestation / prescription ORM models — extracted from models.py (ARCH-2 decomposition).

Pure move of class definitions: same registry, identical tables. Public import
paths ``from app.models.models import X`` / ``from app.models import X`` are
preserved by re-exports in models.py / __init__.py. External classes referenced
only in ``Mapped[...]`` annotations are resolved by SQLAlchemy's class registry
(TYPE_CHECKING import only; no runtime import cycle back into models.py).
"""

from __future__ import annotations

import enum
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import (
    SoftDeleteMixin,
    TenantBaseModel,
    native_enum,
)

if TYPE_CHECKING:  # pragma: no cover - type-checker only; SA resolves via registry
    from app.models.file import File
    from app.models.incidents import Incident
    from app.models.models import (
        Company,
        Person,
        Position,
        Site,
        User,
    )


class InspectionStatus(str, enum.Enum):
    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class InspectionType(str, enum.Enum):
    INTERNAL = "internal"
    EXTERNAL = "external"


class Inspection(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "regulatory_inspection"

    company_id: Mapped[str] = mapped_column(
        ForeignKey("company.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    site_id: Mapped[str | None] = mapped_column(
        ForeignKey("site.id", ondelete="SET NULL"), nullable=True, index=True
    )
    inspection_type: Mapped[InspectionType] = mapped_column(
        native_enum(InspectionType, name="inspectiontype"),
        nullable=False,
        default=InspectionType.INTERNAL,
    )
    responsible_id: Mapped[str | None] = mapped_column(
        ForeignKey("user.id", ondelete="SET NULL"), nullable=True, index=True
    )
    recurrence_rule: Mapped[str | None] = mapped_column(String(128))
    authority: Mapped[str] = mapped_column(String(255), nullable=False)
    purpose: Mapped[str | None] = mapped_column(String(255))
    scheduled_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[InspectionStatus] = mapped_column(
        Enum(InspectionStatus, name="regulatoryinspectionstatus"),
        nullable=False,
        default=InspectionStatus.PLANNED,
    )
    result_summary: Mapped[str | None] = mapped_column(Text)

    company: Mapped[Company] = relationship(backref="regulatory_inspections")
    site: Mapped[Site | None] = relationship(backref="regulatory_inspections")
    responsible: Mapped[User | None] = relationship("User")
    results: Mapped[list["InspectionResult"]] = relationship(
        "InspectionResult",
        back_populates="inspection",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        Index("ix_regulatory_inspection_company", "tenant_id", "company_id"),
        Index("ix_regulatory_inspection_site", "tenant_id", "site_id"),
        Index("ix_regulatory_inspection_responsible", "tenant_id", "responsible_id"),
        Index("ix_regulatory_inspection_status", "tenant_id", "status"),
        Index("ix_regulatory_inspection_type", "tenant_id", "inspection_type"),
    )


class InspectionResult(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "inspection_result"

    inspection_id: Mapped[str] = mapped_column(
        ForeignKey("regulatory_inspection.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    outcome: Mapped[str | None] = mapped_column(String(128))
    notes: Mapped[str | None] = mapped_column(Text)
    issued_at: Mapped[date | None] = mapped_column(Date)
    file_id: Mapped[str | None] = mapped_column(
        ForeignKey("file.id", ondelete="SET NULL"), nullable=True
    )

    inspection: Mapped[Inspection] = relationship(
        "app.models.inspections.Inspection", back_populates="results"
    )
    file: Mapped[File | None] = relationship("File")

    __table_args__ = (
        Index("ix_inspection_result_inspection", "tenant_id", "inspection_id"),
        Index("ix_inspection_result_issued_at", "issued_at"),
    )


class AttestationStatus(str, enum.Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"


class Attestation(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "attestation"

    person_id: Mapped[str] = mapped_column(
        ForeignKey("person.id", ondelete="CASCADE"), nullable=False, index=True
    )
    position_id: Mapped[str | None] = mapped_column(
        ForeignKey("position.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    issued_at: Mapped[date | None] = mapped_column(Date)
    expires_at: Mapped[date | None] = mapped_column(Date)
    status: Mapped[AttestationStatus] = mapped_column(
        native_enum(AttestationStatus, name="attestationstatus"),
        nullable=False,
        default=AttestationStatus.ACTIVE,
    )
    responsible_id: Mapped[str | None] = mapped_column(
        ForeignKey("user.id", ondelete="SET NULL"), nullable=True, index=True
    )
    notes: Mapped[str | None] = mapped_column(Text)

    person: Mapped[Person] = relationship("Person")
    position: Mapped[Position | None] = relationship("Position")
    responsible: Mapped[User | None] = relationship("User")

    __table_args__ = (
        Index("ix_attestation_person", "tenant_id", "person_id"),
        Index("ix_attestation_status", "tenant_id", "status"),
        Index("ix_attestation_expires", "tenant_id", "expires_at"),
    )


class PrescriptionStatus(str, enum.Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    VERIFIED = "verified"
    CANCELLED = "cancelled"


class Prescription(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "inspection_prescription"

    inspection_id: Mapped[str] = mapped_column(
        ForeignKey("regulatory_inspection.id", ondelete="CASCADE"), nullable=False, index=True
    )
    incident_id: Mapped[str | None] = mapped_column(
        ForeignKey("incident.id", ondelete="SET NULL"), nullable=True, index=True
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    due_at: Mapped[date | None] = mapped_column(Date)
    status: Mapped[PrescriptionStatus] = mapped_column(
        native_enum(PrescriptionStatus, name="prescriptionstatus"),
        nullable=False,
        default=PrescriptionStatus.OPEN,
    )
    assignee_id: Mapped[str | None] = mapped_column(
        ForeignKey("user.id", ondelete="SET NULL"), nullable=True, index=True
    )
    evidence: Mapped[str | None] = mapped_column(Text)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    inspection: Mapped[Inspection] = relationship("app.models.inspections.Inspection")
    incident: Mapped[Incident | None] = relationship("Incident")
    assignee: Mapped[User | None] = relationship("User")

    __table_args__ = (
        Index("ix_prescription_inspection", "tenant_id", "inspection_id"),
        Index("ix_prescription_status", "tenant_id", "status"),
        Index("ix_prescription_due", "tenant_id", "due_at"),
        Index("ix_prescription_assignee", "tenant_id", "assignee_id"),
    )
