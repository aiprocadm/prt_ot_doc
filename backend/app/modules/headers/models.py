from __future__ import annotations

from sqlalchemy import Boolean, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.models.base import SoftDeleteMixin, TenantBaseModel

JSONBType = JSONB().with_variant(JSON(), "sqlite")


class HeaderFooterPreset(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "header_footer_presets"

    code: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    different_first: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    different_odd_even: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    header_first_xml: Mapped[str | None] = mapped_column(Text)
    header_odd_xml: Mapped[str | None] = mapped_column(Text)
    header_even_xml: Mapped[str | None] = mapped_column(Text)

    footer_first_xml: Mapped[str | None] = mapped_column(Text)
    footer_odd_xml: Mapped[str | None] = mapped_column(Text)
    footer_even_xml: Mapped[str | None] = mapped_column(Text)

    watermark: Mapped[dict] = mapped_column(JSONBType, nullable=False, default=dict)

    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_header_footer_preset_tenant_code"),
        Index("ix_header_footer_preset_tenant_code", "tenant_id", "code"),
        Index("ix_header_footer_preset_updated_at", "updated_at"),
    )
