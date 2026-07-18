"""Safety core domain models for org structure, risk maps and PPE workflows."""

from __future__ import annotations

import enum
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import TenantBase
from app.models.base import SoftDeleteMixin, TenantBaseModel


class RiskMethodologyType(str, enum.Enum):
    MATRIX = "matrix"
    FINE_KINNEY = "fine_kinney"
    CUSTOM = "custom"


class RecordStatus(str, enum.Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class HazardSourceType(str, enum.Enum):
    PROFESSION = "profession"
    WORK = "work"
    WORKPLACE = "workplace"
    EQUIPMENT = "equipment"
    GENERIC = "generic"


class MeasureType(str, enum.Enum):
    ENGINEERING = "engineering"
    ORGANIZATIONAL = "organizational"
    PPE = "ppe"
    MEDICAL = "medical"
    TRAINING = "training"
    OTHER = "other"


class HazardBindingType(str, enum.Enum):
    POSITION = "position"
    WORKPLACE = "workplace"
    SITE = "site"


class RiskMapEntityType(str, enum.Enum):
    PERSON = "person"
    WORKPLACE = "workplace"
    SITE = "site"


class RiskMapSource(str, enum.Enum):
    MANUAL = "manual"
    IMPORT = "import"
    AUTO_FROM_BINDING = "auto_from_binding"
    INCIDENT_TRIGGER = "incident_trigger"


class RiskLevel(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SafetyRiskMap(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "risk_maps"

    code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    entity_type: Mapped[RiskMapEntityType] = mapped_column(Enum(RiskMapEntityType), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    risk_methodology_id: Mapped[str] = mapped_column(
        ForeignKey("risk_methodologies.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    status: Mapped[RecordStatus] = mapped_column(
        Enum(RecordStatus), nullable=False, default=RecordStatus.DRAFT
    )
    calculated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source: Mapped[RiskMapSource | None] = mapped_column(Enum(RiskMapSource), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)

    __table_args__ = (
        Index(
            "ix_risk_maps_entity_status",
            "tenant_id",
            "entity_type",
            "entity_id",
            "status",
            "updated_at",
        ),
    )


class SafetyRiskMethodology(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "risk_methodologies"

    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[RiskMethodologyType] = mapped_column(Enum(RiskMethodologyType), nullable=False)
    status: Mapped[RecordStatus] = mapped_column(
        Enum(RecordStatus), nullable=False, default=RecordStatus.DRAFT
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    formula_json: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )
    scale_json: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )
    effective_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "code", "version_no", name="uq_risk_methodologies_code_version"
        ),
    )


class Hazard(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "hazards"

    code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_type: Mapped[HazardSourceType | None] = mapped_column(
        Enum(HazardSourceType), nullable=True
    )
    severity_default: Mapped[int | None] = mapped_column(Integer, nullable=True)
    probability_default: Mapped[int | None] = mapped_column(Integer, nullable=True)


class RiskMeasure(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "risk_measures"

    code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    measure_type: Mapped[MeasureType | None] = mapped_column(Enum(MeasureType), nullable=True)
    effectiveness_score: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)


class HazardMeasure(TenantBase):
    __tablename__ = "hazard_measures"
    __tenant_model__ = True

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenant.id"), nullable=False, index=True
    )
    hazard_id: Mapped[str] = mapped_column(
        ForeignKey("hazards.id", ondelete="CASCADE"), nullable=False, index=True
    )
    measure_id: Mapped[str] = mapped_column(
        ForeignKey("risk_measures.id", ondelete="CASCADE"), nullable=False, index=True
    )
    is_recommended: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class HazardBinding(TenantBase):
    __tablename__ = "hazard_bindings"
    __tenant_model__ = True

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenant.id"), nullable=False, index=True
    )
    hazard_id: Mapped[str] = mapped_column(
        ForeignKey("hazards.id", ondelete="CASCADE"), nullable=False, index=True
    )
    binding_type: Mapped[HazardBindingType] = mapped_column(Enum(HazardBindingType), nullable=False)
    binding_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RiskMapItem(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "risk_map_items"

    risk_map_id: Mapped[str] = mapped_column(
        ForeignKey("risk_maps.id", ondelete="CASCADE"), nullable=False, index=True
    )
    hazard_id: Mapped[str] = mapped_column(
        ForeignKey("hazards.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    probability_value: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    severity_value: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    exposure_value: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    raw_score: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    risk_level: Mapped[RiskLevel | None] = mapped_column(Enum(RiskLevel), nullable=True)
    residual_score: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    residual_risk_level: Mapped[RiskLevel | None] = mapped_column(Enum(RiskLevel), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (Index("ix_risk_map_items_level", "risk_map_id", "risk_level"),)


class RiskMapItemMeasure(TenantBase):
    __tablename__ = "risk_map_item_measures"
    __tenant_model__ = True

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenant.id"), nullable=False, index=True
    )
    risk_map_item_id: Mapped[str] = mapped_column(
        ForeignKey("risk_map_items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    measure_id: Mapped[str] = mapped_column(
        ForeignKey("risk_measures.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    measure_order: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="planned")
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    owner_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    effectiveness_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


# PPE family-B ORM classes (PPENorm/PPECatalog/PPENormItem/PPEIssue/
# PPEPersonalCard/PPEPersonalCardItem) were removed in СИЗ Срез-1 (2026-06-10):
# they had no write path and duplicated the live family in models.py (см.
# docs/superpowers/specs/2026-06-10-ppe-norms-personal-card-design.md §7).
# Их таблицы (ppe_norms, ppe_catalog, ...; создавала миграция next58) дропнуты
# миграцией sz02 (20260611_sz02_drop_ppe_family_b_tables).
