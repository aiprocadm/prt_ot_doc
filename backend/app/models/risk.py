"""Tenant-scoped risk assessment models."""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, backref, mapped_column, relationship

from app.db.session import TenantBase
from app.models.base import TenantBaseModel
from app.models.models import Company, Person, Site, Workplace

if TYPE_CHECKING:  # pragma: no cover - imported for typing only
    from app.models.file import File
    from app.models.models import DocumentPack, Position, Workplace

__all__ = [
    "Risk",
    "RiskAssessment",
    "RiskAssessmentItem",
    "RiskCard",
    "RiskActionPlan",
    "RiskActionPlanItem",
    "RiskControl",
    "RiskHazard",
    "RiskMatrixCell",
]


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


def _uuid_str() -> str:
    return str(uuid4())


class RiskHazard(TenantBase):
    """Catalog of hazards scoped to a tenant."""

    __tablename__ = "risk_hazards"
    __tenant_model__ = True

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenant.id"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    module: Mapped[str] = mapped_column(String(32), nullable=False, default="ot")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommended_measures: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, nullable=False, default=list
    )
    document_file_id: Mapped[str | None] = mapped_column(
        ForeignKey("file.id", ondelete="SET NULL"), nullable=True
    )

    document_file: Mapped["File | None"] = relationship("File")
    positions: Mapped[list["Position"]] = relationship(
        "Position",
        secondary="position_hazard",
        lazy="selectin",
        back_populates="hazards",
    )
    workplaces: Mapped[list["Workplace"]] = relationship(
        "Workplace",
        secondary="workplace_hazard",
        lazy="selectin",
        back_populates="hazards",
    )

    __table_args__ = (
        Index("ix_risk_hazard_tenant_code", "tenant_id", "code", unique=True),
    )


class RiskControl(TenantBase):
    """Catalog of mitigation controls grouped by tenant."""

    __tablename__ = "risk_controls"
    __tenant_model__ = True

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenant.id"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False, default="org")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_risk_control_tenant_code", "tenant_id", "code", unique=True),
    )


class RiskMatrixCell(TenantBase):
    """Tenant-specific scoring matrix cell."""

    __tablename__ = "risk_matrix"
    __tenant_model__ = True

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenant.id"), nullable=False, index=True
    )
    severity: Mapped[int] = mapped_column(Integer, nullable=False)
    likelihood: Mapped[int] = mapped_column(Integer, nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    band: Mapped[str] = mapped_column(String(16), nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "severity", "likelihood", name="uq_risk_matrix_cell"),
    )


class RiskAssessment(TenantBase):
    """Stored result of a risk assessment iteration."""

    __tablename__ = "risk_assessments"
    __tenant_model__ = True

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenant.id"), nullable=False, index=True
    )
    assessment_key: Mapped[str] = mapped_column(String(64), nullable=False, default=_uuid_str)
    assessment_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    methodology_id: Mapped[str | None] = mapped_column(
        ForeignKey("riskmethodology.id"), nullable=True, index=True
    )
    methodology_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    company_id: Mapped[str | None] = mapped_column(
        ForeignKey("company.id"), nullable=True, index=True
    )
    place_id: Mapped[str | None] = mapped_column(
        ForeignKey("site.id"), nullable=True, index=True
    )
    workplace_id: Mapped[str | None] = mapped_column(
        ForeignKey("workplace.id"), nullable=True, index=True
    )
    position_id: Mapped[str | None] = mapped_column(
        ForeignKey("position.id"), nullable=True, index=True
    )
    employee_id: Mapped[str | None] = mapped_column(
        ForeignKey("person.id"), nullable=True, index=True
    )
    document_pack_id: Mapped[str | None] = mapped_column(
        ForeignKey("document_pack.id"), nullable=True, index=True
    )
    job_title: Mapped[str | None] = mapped_column(String(128), nullable=True)
    hazard_id: Mapped[str] = mapped_column(ForeignKey("risk_hazards.id"), nullable=False)
    severity_before: Mapped[int] = mapped_column(Integer, nullable=False)
    likelihood_before: Mapped[int] = mapped_column(Integer, nullable=False)
    score_before: Mapped[int] = mapped_column(Integer, nullable=False)
    band_before: Mapped[str] = mapped_column(String(16), nullable=False)
    controls: Mapped[str | None] = mapped_column(Text, nullable=True)
    action_plan: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    risk_card: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    severity_after: Mapped[int] = mapped_column(Integer, nullable=False)
    likelihood_after: Mapped[int] = mapped_column(Integer, nullable=False)
    score_after: Mapped[int] = mapped_column(Integer, nullable=False)
    band_after: Mapped[str] = mapped_column(String(16), nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)

    hazard: Mapped[RiskHazard] = relationship(backref="assessments")
    company: Mapped[Company | None] = relationship(backref="risk_assessments")
    site: Mapped[Site | None] = relationship(backref="risk_assessments")
    workplace: Mapped[Workplace | None] = relationship(backref="risk_assessments")
    position: Mapped["Position | None"] = relationship(backref="risk_assessments")
    employee: Mapped[Person | None] = relationship(backref="risk_assessments")
    document_pack: Mapped["DocumentPack | None"] = relationship(
        backref="risk_assessments"
    )

    __table_args__ = (
        Index("ix_risk_assessment_tenant_job", "tenant_id", "job_title"),
        UniqueConstraint(
            "tenant_id",
            "assessment_key",
            "assessment_version",
            name="uq_risk_assessment_version",
        ),
    )


class Risk(TenantBaseModel):
    """Risk register entry scoped to a tenant."""

    __tablename__ = "risk"

    company_id: Mapped[str] = mapped_column(
        ForeignKey("company.id"), nullable=False, index=True
    )
    site_id: Mapped[str | None] = mapped_column(
        ForeignKey("site.id"), nullable=True, index=True
    )
    hazard: Mapped[str] = mapped_column(String(512), nullable=False)
    probability: Mapped[int] = mapped_column(Integer, nullable=False)
    severity: Mapped[int] = mapped_column(Integer, nullable=False)
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    controls: Mapped[str | None] = mapped_column(Text, nullable=True)

    company: Mapped[Company] = relationship(backref="risks")
    site: Mapped[Site | None] = relationship(backref="risks")

    __table_args__ = (
        Index("ix_risk_tenant_site", "tenant_id", "site_id"),
    )


class RiskAssessmentItem(TenantBaseModel):
    """Detailed hazard-level entry for a risk assessment."""

    __tablename__ = "risk_assessment_items"

    assessment_id: Mapped[str] = mapped_column(
        ForeignKey("risk_assessments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    hazard_id: Mapped[str] = mapped_column(
        ForeignKey("risk_hazards.id", ondelete="CASCADE"), nullable=False, index=True
    )
    probability: Mapped[int] = mapped_column(Integer, nullable=False)
    severity: Mapped[int] = mapped_column(Integer, nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    level: Mapped[str] = mapped_column(String(16), nullable=False)
    methodology_id: Mapped[str | None] = mapped_column(
        ForeignKey("riskmethodology.id"), nullable=True, index=True
    )
    methodology_version: Mapped[int | None] = mapped_column(Integer, nullable=True)

    assessment: Mapped[RiskAssessment] = relationship(backref="items")
    hazard: Mapped[RiskHazard] = relationship(backref="assessment_items")

    __table_args__ = (
        Index("ix_risk_assessment_items_tenant_assessment", "tenant_id", "assessment_id"),
    )


class RiskCard(TenantBaseModel):
    """Stored risk card summary for an assessment scope."""

    __tablename__ = "risk_cards"

    assessment_id: Mapped[str] = mapped_column(
        ForeignKey("risk_assessments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    company_id: Mapped[str | None] = mapped_column(
        ForeignKey("company.id"), nullable=True, index=True
    )
    site_id: Mapped[str | None] = mapped_column(
        ForeignKey("site.id"), nullable=True, index=True
    )
    workplace_id: Mapped[str | None] = mapped_column(
        ForeignKey("workplace.id"), nullable=True, index=True
    )
    position_id: Mapped[str | None] = mapped_column(
        ForeignKey("position.id"), nullable=True, index=True
    )
    employee_id: Mapped[str | None] = mapped_column(
        ForeignKey("person.id"), nullable=True, index=True
    )
    methodology_id: Mapped[str | None] = mapped_column(
        ForeignKey("riskmethodology.id"), nullable=True, index=True
    )
    methodology_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    summary: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    assessment: Mapped[RiskAssessment] = relationship(backref="risk_cards")

    __table_args__ = (
        Index("ix_risk_cards_tenant_assessment", "tenant_id", "assessment_id"),
    )


class RiskActionPlan(TenantBaseModel):
    """Action plan generated from hazards and controls."""

    __tablename__ = "action_plans"

    assessment_id: Mapped[str] = mapped_column(
        ForeignKey("risk_assessments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    company_id: Mapped[str | None] = mapped_column(
        ForeignKey("company.id"), nullable=True, index=True
    )
    site_id: Mapped[str | None] = mapped_column(
        ForeignKey("site.id"), nullable=True, index=True
    )
    workplace_id: Mapped[str | None] = mapped_column(
        ForeignKey("workplace.id"), nullable=True, index=True
    )
    position_id: Mapped[str | None] = mapped_column(
        ForeignKey("position.id"), nullable=True, index=True
    )
    employee_id: Mapped[str | None] = mapped_column(
        ForeignKey("person.id"), nullable=True, index=True
    )
    methodology_id: Mapped[str | None] = mapped_column(
        ForeignKey("riskmethodology.id"), nullable=True, index=True
    )
    methodology_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="open")

    assessment: Mapped[RiskAssessment] = relationship(
        backref=backref("action_plan", uselist=False)
    )

    __table_args__ = (
        Index("ix_action_plans_tenant_assessment", "tenant_id", "assessment_id"),
    )


class RiskActionPlanItem(TenantBaseModel):
    """Action plan line item."""

    __tablename__ = "action_plan_items"

    plan_id: Mapped[str] = mapped_column(
        ForeignKey("action_plans.id", ondelete="CASCADE"), nullable=False, index=True
    )
    assessment_id: Mapped[str] = mapped_column(
        ForeignKey("risk_assessments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    hazard_id: Mapped[str | None] = mapped_column(
        ForeignKey("risk_hazards.id", ondelete="SET NULL"), nullable=True, index=True
    )
    measure_text: Mapped[str] = mapped_column(Text, nullable=False)
    owner_role: Mapped[str | None] = mapped_column(String(64), nullable=True)
    owner_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="planned")
    methodology_id: Mapped[str | None] = mapped_column(
        ForeignKey("riskmethodology.id"), nullable=True, index=True
    )
    methodology_version: Mapped[int | None] = mapped_column(Integer, nullable=True)

    plan: Mapped[RiskActionPlan] = relationship(backref="items")
    assessment: Mapped[RiskAssessment] = relationship(backref="action_plan_items")
    hazard: Mapped[RiskHazard | None] = relationship()

    __table_args__ = (
        Index("ix_action_plan_items_tenant_plan", "tenant_id", "plan_id"),
    )
