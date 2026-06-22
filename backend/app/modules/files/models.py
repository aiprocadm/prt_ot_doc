from __future__ import annotations

from datetime import datetime
from enum import Enum

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db.session import TenantBase
from app.models.base import SoftDeleteMixin, TimestampMixin, UUIDMixin, VersionedMixin

# Canonical file-domain models backing `app.modules.files.api`.


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


class FileContentIndexStatus(str, Enum):
    queued = "queued"
    indexed = "indexed"
    failed = "failed"


class FileStatus(str, Enum):
    uploading = "uploading"
    uploaded = "uploaded"
    scanning = "scanning"
    clean = "clean"
    ready = "ready"
    infected = "infected"
    quarantined = "quarantined"
    deleted = "deleted"


class FileEntityType(str, Enum):
    job = "job"
    job_step = "job_step"
    template = "template"
    template_version = "template_version"
    preset = "preset"
    document = "document"
    person = "person"
    site = "site"
    incident = "incident"
    inspection = "inspection"
    prescription = "prescription"
    report = "report"
    other = "other"


class FileLinkRole(str, Enum):
    source = "source"
    artifact = "artifact"
    log = "log"
    attachment = "attachment"
    signature = "signature"
    certificate = "certificate"
    evidence = "evidence"
    import_file = "import"
    export = "export"


class FileObject(TenantBase, TimestampMixin, SoftDeleteMixin, VersionedMixin, UUIDMixin):
    __tablename__ = "file_objects"
    __tenant_model__ = True

    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenant.id"), nullable=False, index=True
    )
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
    __table_args__ = {"extend_existing": True}

    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenant.id"), nullable=False)
    file_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("file_objects.id"), nullable=False, index=True
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    s3_key: Mapped[str] = mapped_column(String(512), nullable=False)
    size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    mime: Mapped[str] = mapped_column(String(128), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=FileVersionStatus.uploaded.value
    )
    av_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=AVStatus.pending.value
    )
    text_index_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=TextIndexStatus.pending.value
    )
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)


class DownloadLog(TenantBase, TimestampMixin, UUIDMixin):
    __tablename__ = "download_logs"
    __tenant_model__ = True

    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenant.id"), nullable=False, index=True
    )
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    file_id: Mapped[str] = mapped_column(String(36), ForeignKey("file_objects.id"), nullable=False)
    version_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("file_versions.id"), nullable=False
    )
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)


class FileTextIndex(TenantBase, TimestampMixin, UUIDMixin):
    __tablename__ = "file_text_index"
    __tenant_model__ = True

    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenant.id"), nullable=False, index=True
    )
    file_version_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("file_versions.id"), nullable=False, unique=True
    )
    content_tsv: Mapped[str | None] = mapped_column(Text, nullable=True)
    excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    lang: Mapped[str] = mapped_column(String(16), nullable=False, default="simple")
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)


class FileContentIndex(TenantBase, TimestampMixin, SoftDeleteMixin, VersionedMixin, UUIDMixin):
    __tablename__ = "file_content_index"
    __tenant_model__ = True

    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenant.id"), nullable=False, index=True
    )
    file_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("files.id"), nullable=False, unique=True
    )
    doc_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    content_text: Mapped[str | None] = mapped_column(
        TSVECTOR().with_variant(Text(), "sqlite"), nullable=True
    )
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    language: Mapped[str] = mapped_column(String(16), nullable=False, default="ru")
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=FileContentIndexStatus.queued.value
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class FileRecord(TenantBase, TimestampMixin, SoftDeleteMixin, VersionedMixin, UUIDMixin):
    __tablename__ = "files"
    __tenant_model__ = True

    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenant.id"), nullable=False, index=True
    )
    bucket: Mapped[str] = mapped_column(String(255), nullable=False, default="ptd")
    object_key: Mapped[str] = mapped_column(String(512), nullable=False)
    content_type: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=FileStatus.uploaded.value
    )
    av_vendor: Mapped[str | None] = mapped_column(String(64), nullable=True)
    av_result_json: Mapped[dict] = mapped_column(JSON(), nullable=False, default=dict)
    version_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    original_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_public: Mapped[bool] = mapped_column(nullable=False, default=False)
    entity_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    tags: Mapped[dict] = mapped_column(JSON(), nullable=False, default=dict)
    metadata_json: Mapped[dict] = mapped_column(JSON(), nullable=False, default=dict)
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)


class FileLink(TenantBase, TimestampMixin, UUIDMixin):
    __tablename__ = "file_links"
    __tenant_model__ = True

    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenant.id"), nullable=False, index=True
    )
    file_id: Mapped[str] = mapped_column(String(36), ForeignKey("files.id"), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)


class FileDownloadLog(TenantBase, TimestampMixin, UUIDMixin):
    __tablename__ = "file_download_logs"
    __tenant_model__ = True

    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenant.id"), nullable=False, index=True
    )
    file_id: Mapped[str] = mapped_column(String(36), ForeignKey("files.id"), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    purpose: Mapped[str | None] = mapped_column(String(64), nullable=True)
    action: Mapped[str] = mapped_column(String(32), nullable=False, default="presigned_url_issued")


class FileScanResult(TenantBase, TimestampMixin, UUIDMixin):
    __tablename__ = "file_scan_results"
    __tenant_model__ = True

    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenant.id"), nullable=False, index=True
    )
    file_id: Mapped[str] = mapped_column(String(36), ForeignKey("files.id"), nullable=False)
    engine: Mapped[str] = mapped_column(String(32), nullable=False, default="clamav")
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    signature: Mapped[str | None] = mapped_column(String(255), nullable=True)
    scanned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    raw: Mapped[dict] = mapped_column(JSON(), nullable=False, default=dict)


Index(
    "ix_file_versions_tenant_status_updated",
    FileVersion.tenant_id,
    FileVersion.status,
    FileVersion.updated_at,
)
Index(
    "ix_file_objects_owner",
    FileObject.tenant_id,
    FileObject.owner_entity_type,
    FileObject.owner_entity_id,
)
Index("ix_files_tenant_sha256", FileRecord.tenant_id, FileRecord.sha256)
Index("ix_files_tenant_updated_at", FileRecord.tenant_id, FileRecord.updated_at)
Index("ix_files_tenant_status", FileRecord.tenant_id, FileRecord.status)
Index("ix_files_tenant_entity", FileRecord.tenant_id, FileRecord.entity_type, FileRecord.entity_id)
Index("ix_files_tags_gin", FileRecord.tags, postgresql_using="gin")
Index("ix_file_links_tenant_entity", FileLink.tenant_id, FileLink.entity_type, FileLink.entity_id)
Index(
    "ix_file_download_logs_tenant_file_created",
    FileDownloadLog.tenant_id,
    FileDownloadLog.file_id,
    FileDownloadLog.created_at,
)
Index(
    "ix_file_download_logs_tenant_created_at", FileDownloadLog.tenant_id, FileDownloadLog.created_at
)
Index("ix_files_tenant_object_key", FileRecord.tenant_id, FileRecord.object_key, unique=True)
Index("ix_file_content_index_status_updated", FileContentIndex.status, FileContentIndex.updated_at)
Index("ix_file_scan_results_file_scanned", FileScanResult.file_id, FileScanResult.scanned_at)
