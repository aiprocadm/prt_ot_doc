from __future__ import annotations

from enum import Enum

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db.session import TenantBase
from app.models.base import SoftDeleteMixin, TimestampMixin, UUIDMixin, VersionedMixin


class FileVersionStatus(str, Enum):
    uploaded = "uploaded"
    scanning = "scanning"
    ready = "ready"
    quarantined = "quarantined"
    rejected = "rejected"


class AVStatus(str, Enum):
    pending = "pending"
    clean = "clean"
    infected = "infected"
    error = "error"


class TextIndexStatus(str, Enum):
    pending = "pending"
    indexed = "indexed"
    skipped = "skipped"
    error = "error"


class FileObject(TenantBase, TimestampMixin, SoftDeleteMixin, VersionedMixin, UUIDMixin):
    __tablename__ = "file_objects"
    __tenant_model__ = True

    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenant.id"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    owner_entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    owner_entity_id: Mapped[str] = mapped_column(String(64), nullable=False)
    tags: Mapped[list[str]] = mapped_column(
        ARRAY(String()).with_variant(JSON(), "sqlite"),
        nullable=False,
        default=list,
    )


class FileVersion(TenantBase, TimestampMixin, VersionedMixin, UUIDMixin):
    __tablename__ = "file_versions"
    __tenant_model__ = True

    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenant.id"), nullable=False, index=True)
    file_id: Mapped[str] = mapped_column(String(36), ForeignKey("file_objects.id"), nullable=False, index=True)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    s3_key: Mapped[str] = mapped_column(String(512), nullable=False)
    size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    mime: Mapped[str] = mapped_column(String(128), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=FileVersionStatus.uploaded.value)
    av_status: Mapped[str] = mapped_column(String(32), nullable=False, default=AVStatus.pending.value)
    text_index_status: Mapped[str] = mapped_column(String(32), nullable=False, default=TextIndexStatus.pending.value)
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)


class DownloadLog(TenantBase, TimestampMixin, UUIDMixin):
    __tablename__ = "download_logs"
    __tenant_model__ = True

    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenant.id"), nullable=False, index=True)
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    file_id: Mapped[str] = mapped_column(String(36), ForeignKey("file_objects.id"), nullable=False)
    version_id: Mapped[str] = mapped_column(String(36), ForeignKey("file_versions.id"), nullable=False)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)


class FileTextIndex(TenantBase, TimestampMixin, UUIDMixin):
    __tablename__ = "file_text_index"
    __tenant_model__ = True

    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenant.id"), nullable=False, index=True)
    file_version_id: Mapped[str] = mapped_column(String(36), ForeignKey("file_versions.id"), nullable=False, unique=True)
    content_tsv: Mapped[str | None] = mapped_column(Text, nullable=True)
    excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    lang: Mapped[str] = mapped_column(String(16), nullable=False, default="simple")
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)


Index("ix_file_versions_tenant_status_updated", FileVersion.tenant_id, FileVersion.status, FileVersion.updated_at)
Index("ix_file_objects_owner", FileObject.tenant_id, FileObject.owner_entity_type, FileObject.owner_entity_id)
