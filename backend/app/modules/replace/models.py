from __future__ import annotations

import enum

from datetime import datetime, timezone

from sqlalchemy import DateTime, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.models.base import SoftDeleteMixin, TenantBaseModel

JSONBType = JSONB().with_variant(JSON(), "sqlite")


class ReplaceRunMode(str, enum.Enum):
    DRY_RUN = "dry_run"
    APPLY = "apply"


class ReplaceRunStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ReplaceMap(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "replace_map"

    code: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(String(16), nullable=False, default="inline")
    rules: Mapped[list[dict]] = mapped_column(JSONBType, nullable=False, default=list)
    exclusions: Mapped[dict] = mapped_column(JSONBType, nullable=False, default=dict)

    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_replace_map_tenant_code"),
        Index("ix_replace_map_tenant_code", "tenant_id", "code"),
        Index("ix_replace_map_updated_at", "updated_at"),
    )


class ReplaceRun(TenantBaseModel):
    __tablename__ = "replace_run"

    document_version_id: Mapped[str] = mapped_column(String(36), nullable=False)
    replace_map_id: Mapped[str] = mapped_column(String(36), nullable=False)
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    options: Mapped[dict] = mapped_column(JSONBType, nullable=False, default=dict)
    report_json: Mapped[dict] = mapped_column(JSONBType, nullable=False, default=dict)
    before_file_id: Mapped[str] = mapped_column(String(512), nullable=False)
    after_file_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=ReplaceRunStatus.QUEUED.value)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_payload: Mapped[dict | None] = mapped_column(JSONBType, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    __table_args__ = (
        Index("ix_replace_run_tenant_created", "tenant_id", "created_at"),
        Index("ix_replace_run_document", "tenant_id", "document_version_id"),
    )
