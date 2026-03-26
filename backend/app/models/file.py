"""File metadata model for tenant-scoped storage objects."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from sqlalchemy import BigInteger, Boolean, DateTime, Index, String
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.models.base import TenantBaseModel

JSONBType = JSONB().with_variant(JSON(), "sqlite")

__all__ = ["File", "FileKind", "FileScanStatus"]


class FileScanStatus(str, Enum):
    """Normalized antivirus scan states used across the application."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    CLEAN = "clean"
    INFECTED = "infected"
    ERROR = "error"


class FileKind(str, Enum):
    """Supported business-level file categories."""

    TEMPLATE = "template"
    DOCUMENT = "document"
    ARCHIVE = "archive"
    DRAFT = "draft"
    ATTACHMENT = "attachment"
    OTHER = "other"


class File(TenantBaseModel):
    """Stores metadata about files uploaded to object storage."""

    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    bucket: Mapped[str] = mapped_column(String(255), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    mime: Mapped[str] = mapped_column(String(128), nullable=False)
    original_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    meta_json: Mapped[dict] = mapped_column(JSONBType, nullable=False, default=dict)
    kind: Mapped[FileKind] = mapped_column(
        SQLEnum(FileKind, name="file_kind"), nullable=False, default=FileKind.DOCUMENT
    )
    company_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    pack_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    is_quarantined: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    scan_status: Mapped[FileScanStatus] = mapped_column(
        SQLEnum(FileScanStatus, name="file_scan_status"),
        nullable=False,
        default=FileScanStatus.PENDING,
    )
    clamav_signature: Mapped[str | None] = mapped_column(String(255), nullable=True)
    clamav_scanned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_file_storage_key", "tenant_id", "storage_key", unique=True),
        Index("ix_file_sha256", "tenant_id", "sha256"),
        Index("ix_file_kind", "tenant_id", "kind"),
        Index("ix_file_pack", "tenant_id", "pack_id"),
    )
