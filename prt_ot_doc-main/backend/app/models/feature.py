"""Feature flag models supporting per-tenant enablement."""

from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.models.base import SharedModel, TenantBaseModel

JSONBType = JSONB().with_variant(JSON(), "sqlite")

__all__ = ["Feature", "FeatureEnablement"]


class Feature(SharedModel):
    """Global feature flag definition available to all tenants."""

    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)

    __table_args__ = (UniqueConstraint("code", name="uq_feature_code"),)


class FeatureEnablement(TenantBaseModel):
    """Associates a feature flag with a tenant."""

    feature_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("feature.id", ondelete="CASCADE"),
        nullable=False,
    )
    on: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    config_json: Mapped[dict] = mapped_column(JSONBType, nullable=False, default=dict)

    __table_args__ = (
        UniqueConstraint("tenant_id", "feature_id", name="uq_feature_enablement_tenant_feature"),
        Index("ix_feature_enablement_feature_id", "feature_id"),
        Index("ix_feature_enablement_on", "on"),
    )
