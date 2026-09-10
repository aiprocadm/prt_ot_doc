from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import SoftDeleteMixin, TenantBaseModel


class Finding(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "findings"
    __table_args__ = (
        Index(
            "ix_findings_tenant_source_status_severity",
            "tenant_id",
            "source_type",
            "source_id",
            "status",
            "severity",
        ),
    )

    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    source_id: Mapped[str] = mapped_column(String(36), nullable=False)
    site_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("site.id", ondelete="SET NULL"), nullable=True
    )
    department_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("department.id", ondelete="SET NULL"), nullable=True
    )
    workplace_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    person_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("person.id", ondelete="SET NULL"), nullable=True
    )
    risk_map_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    severity: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="open")
    finding_type: Mapped[str] = mapped_column(Text, nullable=False)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)


class OpsPrescription(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "ops_prescriptions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_ops_prescriptions_tenant_code"),
        Index("ix_ops_prescriptions_tenant_status_due", "tenant_id", "status", "due_date"),
    )

    code: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    source_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    issuer_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="draft")


class CorrectiveAction(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "corrective_actions"
    __table_args__ = (
        Index(
            "ix_corrective_actions_tenant_responsible_status_due",
            "tenant_id",
            "responsible_user_id",
            "status",
            "due_date",
        ),
    )

    code: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    source_id: Mapped[str] = mapped_column(String(36), nullable=False)
    site_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("site.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    action_type: Mapped[str] = mapped_column(Text, nullable=False)
    responsible_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verification_due_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    verification_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="open")
    effectiveness_status: Mapped[str | None] = mapped_column(Text, nullable=True)


class InspectionPrepPackage(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "inspection_prep_packages"
    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_inspection_prep_packages_tenant_code"),
        Index(
            "ix_inspection_prep_packages_tenant_site_status_target",
            "tenant_id",
            "site_id",
            "status",
            "target_inspection_date",
        ),
    )

    code: Mapped[str] = mapped_column(Text, nullable=False)
    company_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("company.id", ondelete="SET NULL"), nullable=True
    )
    site_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("site.id", ondelete="SET NULL"), nullable=True
    )
    contractor_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    package_type: Mapped[str] = mapped_column(Text, nullable=False, default="inspection_prep")
    status: Mapped[str] = mapped_column(Text, nullable=False, default="draft")
    target_inspection_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class InspectionPrepItem(TenantBaseModel):
    __tablename__ = "inspection_prep_items"

    package_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("inspection_prep_packages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    item_type: Mapped[str] = mapped_column(Text, nullable=False)
    reference_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="required")
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class InspectionPrepGap(TenantBaseModel):
    __tablename__ = "inspection_prep_gaps"

    package_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("inspection_prep_packages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    gap_type: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    severity: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    corrective_action_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("corrective_actions.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, default="open")
