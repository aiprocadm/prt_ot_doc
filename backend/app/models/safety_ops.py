from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import SoftDeleteMixin, TenantBaseModel


class IncidentCase(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "incident_cases"
    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_incident_cases_tenant_code"),
        Index(
            "ix_incident_cases_tenant_site_status_severity_occurred",
            "tenant_id",
            "site_id",
            "status",
            "severity",
            "occurred_at",
        ),
    )

    code: Mapped[str] = mapped_column(Text, nullable=False)
    company_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("company.id", ondelete="SET NULL"), nullable=True
    )
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
    contractor_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    incident_type: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="draft")
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    detected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    registered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    consequences: Mapped[str | None] = mapped_column(Text, nullable=True)
    root_cause_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    external_report_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    linked_risk_review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)


class IncidentPerson(TenantBaseModel):
    __tablename__ = "incident_persons"

    incident_case_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("incident_cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    person_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("person.id", ondelete="SET NULL"), nullable=True
    )
    role: Mapped[str] = mapped_column(Text, nullable=False)
    fio_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class IncidentInvestigation(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "incident_investigations"

    incident_case_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("incident_cases.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, default="draft")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    methodology: Mapped[str | None] = mapped_column(Text, nullable=True)
    findings_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    causes_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    recommendations_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)


class IncidentAttachment(TenantBaseModel):
    __tablename__ = "incident_attachments"

    incident_case_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("incident_cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    file_id: Mapped[str] = mapped_column(String(36), nullable=False)
    attachment_type: Mapped[str] = mapped_column(Text, nullable=False)


class InspectionPlan(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "inspection_plans"

    code: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    plan_type: Mapped[str] = mapped_column(Text, nullable=False)
    period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="draft")


class InspectionPlanItem(TenantBaseModel):
    __tablename__ = "inspection_plan_items"

    inspection_plan_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("inspection_plans.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    site_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("site.id", ondelete="SET NULL"), nullable=True
    )
    department_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("department.id", ondelete="SET NULL"), nullable=True
    )
    contractor_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    planned_for: Mapped[date] = mapped_column(Date, nullable=False)
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="planned")


class OpsInspection(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "ops_inspections"
    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_ops_inspections_tenant_code"),
        Index(
            "ix_ops_inspections_tenant_site_status_type_started",
            "tenant_id",
            "site_id",
            "status",
            "inspection_type",
            "started_at",
        ),
    )

    code: Mapped[str] = mapped_column(Text, nullable=False)
    plan_item_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("inspection_plan_items.id", ondelete="SET NULL"), nullable=True
    )
    inspection_type: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False, default="manual")
    company_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("company.id", ondelete="SET NULL"), nullable=True
    )
    site_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("site.id", ondelete="SET NULL"), nullable=True
    )
    department_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("department.id", ondelete="SET NULL"), nullable=True
    )
    contractor_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="draft")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    inspector_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class InspectionChecklist(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "inspection_checklists"

    code: Mapped[str | None] = mapped_column(Text, nullable=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    checklist_type: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="draft")


class InspectionChecklistItem(TenantBaseModel):
    __tablename__ = "inspection_checklist_items"

    inspection_checklist_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("inspection_checklists.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    code: Mapped[str | None] = mapped_column(Text, nullable=True)
    section: Mapped[str | None] = mapped_column(Text, nullable=True)
    item_order: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    normative_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    severity_if_failed: Mapped[str | None] = mapped_column(Text, nullable=True)


class InspectionRun(TenantBaseModel):
    __tablename__ = "inspection_runs"

    inspection_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("ops_inspections.id", ondelete="CASCADE"), nullable=False, index=True
    )
    inspection_checklist_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("inspection_checklists.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, default="in_progress")


class InspectionRunItem(TenantBaseModel):
    __tablename__ = "inspection_run_items"

    inspection_run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("inspection_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    checklist_item_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("inspection_checklist_items.id", ondelete="RESTRICT"), nullable=False
    )
    result: Mapped[str] = mapped_column(Text, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class InspectionAttachment(TenantBaseModel):
    __tablename__ = "inspection_attachments"

    inspection_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("ops_inspections.id", ondelete="CASCADE"), nullable=False, index=True
    )
    file_id: Mapped[str] = mapped_column(String(36), nullable=False)
    attachment_type: Mapped[str] = mapped_column(Text, nullable=False)


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


class PrescriptionItem(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "prescription_items"

    prescription_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("ops_prescriptions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    finding_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("findings.id", ondelete="SET NULL"), nullable=True
    )
    item_order: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    responsible_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="open")


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


class CorrectiveActionAttachment(TenantBaseModel):
    __tablename__ = "corrective_action_attachments"

    corrective_action_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("corrective_actions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    file_id: Mapped[str] = mapped_column(String(36), nullable=False)
    attachment_type: Mapped[str] = mapped_column(Text, nullable=False)


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
    source_inspection_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("ops_inspections.id", ondelete="SET NULL"), nullable=True
    )
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
