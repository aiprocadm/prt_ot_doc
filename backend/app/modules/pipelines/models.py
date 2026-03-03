from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.models.base import TenantBaseModel

JSONBType = JSONB().with_variant(JSON(), "sqlite")


class PipelineProfile(TenantBaseModel):
    __tablename__ = "pipeline_profiles"

    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    steps: Mapped[list[dict]] = mapped_column(JSONBType, nullable=False, default=list)
    graph: Mapped[dict] = mapped_column(JSONBType, nullable=False, default=dict)
    limits: Mapped[dict] = mapped_column(JSONBType, nullable=False, default=dict)
    concurrency_limit_per_tenant: Mapped[int | None] = mapped_column(Integer, nullable=True)
    profile_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_pipeline_profile_tenant_code"),
        Index("ix_pipeline_profiles_tenant_active", "tenant_id", "is_active"),
    )


class PipelinePackageProfile(TenantBaseModel):
    """Package profile for document job orchestrator compatibility."""

    __tablename__ = "package_profiles"

    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    steps_json: Mapped[list[dict]] = mapped_column(JSONBType, nullable=False, default=list)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_package_profile_tenant_code"),
        Index("ix_package_profiles_tenant_code", "tenant_id", "code"),
    )
