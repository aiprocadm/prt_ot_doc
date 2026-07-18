"""Template-catalog ORM models — extracted from models.py (ARCH-2 decomposition).

Pure move of class definitions: same registry, identical tables. Public import
paths ``from app.models.models import X`` / ``from app.models import X`` are
preserved by re-exports in models.py / __init__.py. External classes referenced
only in ``Mapped[...]`` annotations are resolved by SQLAlchemy's class registry
(TYPE_CHECKING import only; no runtime import cycle back into models.py).
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    UniqueConstraint,
)
from sqlalchemy.ext.mutable import MutableDict, MutableList
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import (
    TenantBaseModel,
)

if TYPE_CHECKING:  # pragma: no cover - type-checker only; SA resolves via registry
    pass


class TemplateStatus(str, enum.Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class Template(TenantBaseModel):
    code: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(String(1024))
    category: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    scope_level: Mapped[str] = mapped_column(
        String(32), nullable=False, default="tenant", index=True
    )
    scope_company_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    scope_site_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    tags_json: Mapped[list[str] | None] = mapped_column(MutableList.as_mutable(JSON), nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )
    storage_key: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)
    status: Mapped[TemplateStatus] = mapped_column(
        Enum(TemplateStatus), nullable=False, default=TemplateStatus.DRAFT
    )
    current_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("templateversion.id", ondelete="SET NULL"), nullable=True, index=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_templates_tenant_code"),
        Index("ix_template_status_updated", "tenant_id", "status", "updated_at"),
        Index("ix_template_updated", "tenant_id", "updated_at"),
        Index(
            "ix_template_scope_level_company_site",
            "tenant_id",
            "scope_level",
            "scope_company_id",
            "scope_site_id",
        ),
    )


class TemplateVersionStatus(str, enum.Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"
    UPLOADED = "uploaded"
    LINTED = "linted"
    READY = "ready"
    DEPRECATED = "deprecated"


class TemplateVersion(TenantBaseModel):
    template_id: Mapped[str] = mapped_column(ForeignKey("template.id"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    checksum: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[TemplateVersionStatus] = mapped_column(
        Enum(TemplateVersionStatus), nullable=False, default=TemplateVersionStatus.UPLOADED
    )
    payload_key: Mapped[str] = mapped_column(String(512), nullable=False)
    file_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    placeholder_index: Mapped[dict[str, Any] | None] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=True
    )
    linter_report_json: Mapped[dict[str, Any] | None] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=True
    )
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    document_type: Mapped[str | None] = mapped_column(String(255))
    required_fields_schema: Mapped[dict[str, Any] | None] = mapped_column(
        MutableDict.as_mutable(JSON)
    )
    applicability_rules: Mapped[dict[str, Any] | None] = mapped_column(MutableDict.as_mutable(JSON))
    output_types: Mapped[list[str] | None] = mapped_column(MutableList.as_mutable(JSON))
    profile: Mapped[dict[str, Any] | None] = mapped_column(MutableDict.as_mutable(JSON))

    template: Mapped[Template] = relationship(backref="versions", foreign_keys=[template_id])

    __mapper_args__ = {
        "version_id_generator": False,
    }

    __table_args__ = (
        UniqueConstraint("template_id", "version", name="uq_template_version"),
        Index("ix_template_version_status", "tenant_id", "status"),
        Index("ix_template_version_updated", "tenant_id", "updated_at"),
    )


class TemplateUsage(TenantBaseModel):
    template_version_id: Mapped[str] = mapped_column(
        ForeignKey("templateversion.id"), nullable=False, index=True
    )
    used_by_type: Mapped[str] = mapped_column(String(64), nullable=False)
    used_by_id: Mapped[str] = mapped_column(String(36), nullable=False)

    template_version: Mapped[TemplateVersion] = relationship(backref="usages")

    __table_args__ = (
        UniqueConstraint(
            "template_version_id",
            "used_by_type",
            "used_by_id",
            name="uq_template_usage_target",
        ),
        Index("ix_template_usage_lookup", "tenant_id", "template_version_id"),
    )
