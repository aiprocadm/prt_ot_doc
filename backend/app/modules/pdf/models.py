from __future__ import annotations

import enum

from sqlalchemy import ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.models.base import TenantBaseModel

JSONBType = JSONB().with_variant(JSON(), "sqlite")


class PdfRunStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELED = "canceled"


class PdfConversionRun(TenantBaseModel):
    __tablename__ = "pdf_conversion_runs"

    input_file_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("file.id", ondelete="CASCADE"), nullable=False
    )
    output_file_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("file.id", ondelete="SET NULL"), nullable=True
    )
    source_document_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[PdfRunStatus] = mapped_column(
        String(16), nullable=False, default=PdfRunStatus.QUEUED.value
    )
    timeout_s: Mapped[int] = mapped_column(Integer, nullable=False, default=45)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_payload: Mapped[dict] = mapped_column(JSONBType, nullable=False, default=dict)
    correlation_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)

    __table_args__ = (
        Index("ix_pdf_runs_tenant_status", "tenant_id", "status"),
        Index("ix_pdf_runs_input", "tenant_id", "input_file_id"),
    )
