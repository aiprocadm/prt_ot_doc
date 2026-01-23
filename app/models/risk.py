"""Tenant-scoped risk assessment models."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import TenantBase
from app.models.base import TenantBaseModel
from app.models.models import Company, Site

if TYPE_CHECKING:  # pragma: no cover - imported for typing only
    from app.models.file import File
    from app.models.models import DocumentPack, Position, Workplace

__all__ = [
    "Risk",
    "RiskAssessment",
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
    company_id: Mapped[str | None] = mapped_column(
        ForeignKey("company.id"), nullable=True, index=True
    )
    place_id: Mapped[str | None] = mapped_column(
        ForeignKey("site.id"), nullable=True, index=True
    )
    position_id: Mapped[str | None] = mapped_column(
        ForeignKey("position.id"), nullable=True, index=True
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
    severity_after: Mapped[int] = mapped_column(Integer, nullable=False)
    likelihood_after: Mapped[int] = mapped_column(Integer, nullable=False)
    score_after: Mapped[int] = mapped_column(Integer, nullable=False)
    band_after: Mapped[str] = mapped_column(String(16), nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)

    hazard: Mapped[RiskHazard] = relationship(backref="assessments")
    company: Mapped[Company | None] = relationship(backref="risk_assessments")
    site: Mapped[Site | None] = relationship(backref="risk_assessments")
    position: Mapped["Position | None"] = relationship(backref="risk_assessments")
    document_pack: Mapped["DocumentPack | None"] = relationship(
        backref="risk_assessments"
    )

    __table_args__ = (
        Index("ix_risk_assessment_tenant_job", "tenant_id", "job_title"),
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
