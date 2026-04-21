from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import SoftDeleteMixin, TenantBaseModel


class ComplianceStatus(str, enum.Enum):
    VALID = "valid"
    PENDING = "pending"
    EXPIRED = "expired"
    BLOCKED = "blocked"


class IncidentSeverity(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ContractorRegistry(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "contractor_registry"

    company_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    legal_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    inn: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    contact_person: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        Index("ix_contractor_registry_tenant_status", "tenant_id", "status"),
        Index("ix_contractor_registry_tenant_company", "tenant_id", "company_id"),
    )


class ContractorEmployee(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "contractor_employees"

    contractor_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("contractor_registry.id", ondelete="CASCADE"), nullable=False, index=True
    )
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    position: Mapped[str | None] = mapped_column(String(255), nullable=True)
    personnel_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    access_status: Mapped[ComplianceStatus] = mapped_column(
        Enum(ComplianceStatus, name="contractor_access_status"), nullable=False, default=ComplianceStatus.PENDING
    )
    training_status: Mapped[ComplianceStatus] = mapped_column(
        Enum(ComplianceStatus, name="contractor_training_status"), nullable=False, default=ComplianceStatus.PENDING
    )
    medical_status: Mapped[ComplianceStatus] = mapped_column(
        Enum(ComplianceStatus, name="contractor_medical_status"), nullable=False, default=ComplianceStatus.PENDING
    )
    last_training_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_medical_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_contractor_employees_tenant_contractor", "tenant_id", "contractor_id"),
        Index("ix_contractor_employees_tenant_training", "tenant_id", "training_status"),
        Index("ix_contractor_employees_tenant_medical", "tenant_id", "medical_status"),
    )


class ContractorIncident(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "contractor_incidents"

    contractor_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("contractor_registry.id", ondelete="CASCADE"), nullable=False, index=True
    )
    employee_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("contractor_employees.id", ondelete="SET NULL"), nullable=True, index=True
    )
    incident_type: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[IncidentSeverity] = mapped_column(
        Enum(IncidentSeverity, name="contractor_incident_severity"), nullable=False, default=IncidentSeverity.MEDIUM
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="open")
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_contractor_incidents_tenant_contractor", "tenant_id", "contractor_id"),
        Index("ix_contractor_incidents_tenant_status", "tenant_id", "status"),
    )
