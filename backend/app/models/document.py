"""Document domain models."""

from __future__ import annotations

import enum
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship, synonym, validates
from sqlalchemy.types import JSON

from app.models.base import TenantBaseModel, native_enum
from app.models.file import File
from app.models.finance import Contract, Department, Invoice, Order
from app.models.models import Company, DocumentPack, Person, Template, TemplateVersion, User

JSONBType = JSONB().with_variant(JSON(), "sqlite")


class DocumentStatus(str, enum.Enum):
    """Lifecycle states of a document."""

    DRAFT = "draft"
    GENERATED = "generated"
    REVIEW = "review"
    APPROVED = "approved"
    SIGNED = "signed"
    ARCHIVED = "archived"
    REVOKED = "revoked"


class Document(TenantBaseModel):
    """Tenant-scoped document entity."""

    company_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("company.id", ondelete="CASCADE"), nullable=False
    )
    person_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("person.id", ondelete="SET NULL"), nullable=True
    )
    site_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("site.id", ondelete="SET NULL"), nullable=True
    )
    department_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("department.id", ondelete="SET NULL"), nullable=True
    )
    contract_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("contract.id", ondelete="SET NULL"), nullable=True
    )
    order_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("order.id", ondelete="SET NULL"), nullable=True
    )
    invoice_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("invoice.id", ondelete="SET NULL"), nullable=True
    )
    template_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("template.id", ondelete="RESTRICT"), nullable=False
    )
    template_version_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("templateversion.id", ondelete="RESTRICT"), nullable=True
    )
    status: Mapped[DocumentStatus] = mapped_column(
        native_enum(DocumentStatus, name="documentstatus"),
        nullable=False,
        default=DocumentStatus.DRAFT,
    )
    storage_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("file.id", ondelete="SET NULL"), nullable=True
    )
    signed_file_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("file.id", ondelete="SET NULL"), nullable=True
    )
    content_sha256: Mapped[str | None] = mapped_column(String(64))
    created_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("user.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(tz=timezone.utc),
        nullable=False,
    )
    job_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("documentgenerationjob.id", ondelete="SET NULL"), nullable=True
    )

    company = relationship("Company", backref="documents")
    person = relationship("Person", backref="documents")
    site = relationship("Site", backref="documents")
    department: Mapped[Department | None] = relationship("Department", backref="documents")
    contract: Mapped[Contract | None] = relationship("Contract", backref="documents")
    order: Mapped[Order | None] = relationship("Order", backref="documents")
    invoice: Mapped[Invoice | None] = relationship("Invoice", backref="documents")
    template = relationship("Template", backref="documents")
    template_version = relationship("TemplateVersion", backref="documents")
    creator = relationship("User", backref="documents_created", foreign_keys=[created_by])
    file: Mapped[File | None] = relationship(
        File, foreign_keys=[file_id], lazy="selectin", backref="documents"
    )
    signed_file: Mapped[File | None] = relationship(
        File, foreign_keys=[signed_file_id], lazy="selectin", backref="signed_documents"
    )
    job = relationship(
        "DocumentGenerationJob",
        back_populates="source_documents",
        foreign_keys=[job_id],
    )
    versions = relationship(
        "DocumentVersion",
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="DocumentVersion.created_at",
        lazy="selectin",
    )
    generation_jobs = relationship(
        "DocumentGenerationJob",
        back_populates="document",
        cascade="all, delete-orphan",
        foreign_keys="DocumentGenerationJob.document_id",
    )

    __table_args__ = (
        Index("ix_document_created_at", "created_at"),
        Index("ix_document_tenant_created_at", "tenant_id", "created_at"),
        Index("ix_document_status", "status"),
        Index("ix_document_template_version", "tenant_id", "template_version_id"),
        Index("ix_document_site", "tenant_id", "site_id"),
        Index("ix_document_job", "tenant_id", "job_id"),
    )


class DocumentVersionStatus(str, enum.Enum):
    """State of a persisted document revision."""

    DRAFT = "draft"
    LOCKED = "locked"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class DocumentVersion(TenantBaseModel):
    """Immutable snapshot of a document revision."""

    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("document.id", ondelete="CASCADE"), nullable=False
    )
    snapshot_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("document_snapshot.id", ondelete="SET NULL"), nullable=True
    )
    template_version: Mapped[str] = mapped_column(Text, nullable=False)
    data_json: Mapped[dict] = mapped_column(JSONBType, nullable=False, default=dict)
    file_key: Mapped[str] = mapped_column(Text, nullable=False)
    file_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("file.id", ondelete="SET NULL"), nullable=True
    )
    template_version_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("templateversion.id", ondelete="SET NULL"), nullable=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[DocumentVersionStatus] = mapped_column(
        Enum(
            DocumentVersionStatus,
            name="documentversionstatus",
            # iter-19 RB-002g cohort closure: PG type `documentversionstatus`
            # was created lowercase by migration 8d2c1a6c5e24:55-58. Member
            # names are uppercase, so default SQLAlchemy binding sends "DRAFT"
            # → asyncpg rejects. Force `.value` (lowercase) via callable.
            # Pinned by `backend/tests/test_documentversion_status_enum_values.py`.
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=DocumentVersionStatus.DRAFT,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(tz=timezone.utc),
        nullable=False,
    )
    approval_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    signature_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    edo_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    document = relationship("Document", back_populates="versions")
    snapshot: Mapped["DocumentSnapshot | None"] = relationship(
        "DocumentSnapshot", back_populates="document_version", lazy="selectin"
    )
    file: Mapped[File | None] = relationship(File, foreign_keys=[file_id], lazy="selectin")
    template_version_ref: Mapped[TemplateVersion | None] = relationship(
        TemplateVersion, foreign_keys=[template_version_id], lazy="selectin"
    )

    if TYPE_CHECKING:  # pragma: no cover - type checking only
        tenant_id: Mapped[str]

    __table_args__ = (
        Index("ix_document_version_document_id", "document_id"),
        Index("ix_document_version_created_at", "created_at"),
        Index("ix_document_version_template_version", "tenant_id", "template_version_id"),
    )

    @validates("document")
    def _sync_tenant_from_document(self, key, document):  # type: ignore[override]
        if document is not None:
            self.tenant_id = document.tenant_id
        return document


class DocumentSnapshot(TenantBaseModel):
    """Immutable snapshot of document context at generation time."""

    __tablename__ = "document_snapshot"

    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("document.id", ondelete="CASCADE"), nullable=False
    )
    template_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("template.id", ondelete="RESTRICT"), nullable=False
    )
    template_version_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("templateversion.id", ondelete="SET NULL"), nullable=True
    )
    template_code: Mapped[str] = mapped_column(String(255), nullable=False)
    template_version: Mapped[int | None] = mapped_column(Integer)
    company_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONBType, nullable=False, default=dict
    )
    source_refs: Mapped[dict[str, Any]] = mapped_column(JSONBType, nullable=False, default=dict)
    compliance_refs: Mapped[dict[str, Any]] = mapped_column(JSONBType, nullable=False, default=dict)
    render_log: Mapped[dict[str, Any]] = mapped_column(JSONBType, nullable=False, default=dict)
    integrity_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(tz=timezone.utc),
        nullable=False,
    )
    created_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("user.id", ondelete="RESTRICT"), nullable=False
    )

    document = relationship("Document", backref="snapshots")
    document_version: Mapped[DocumentVersion | None] = relationship(
        "DocumentVersion", back_populates="snapshot", uselist=False
    )
    template = relationship(Template)
    template_version_ref: Mapped[TemplateVersion | None] = relationship(
        TemplateVersion, foreign_keys=[template_version_id]
    )
    creator = relationship(User, foreign_keys=[created_by])

    __table_args__ = (
        Index("ix_document_snapshot_document", "document_id"),
        Index("ix_document_snapshot_template", "tenant_id", "template_id"),
    )


class DocumentJobStatus(str, enum.Enum):
    """Lifecycle of asynchronous document generation jobs."""

    QUEUED = "queued"
    PROCESSING = "processing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class DocumentGenerationJob(TenantBaseModel):
    """Tracks document generation requests for idempotency and auditing."""

    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    task_id: Mapped[str] = mapped_column(String(128), nullable=False)
    template_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("template.id", ondelete="RESTRICT"), nullable=False
    )
    template_code: Mapped[str] = mapped_column(String(255), nullable=False)
    company_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("company.id", ondelete="RESTRICT"), nullable=False
    )
    person_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("person.id", ondelete="SET NULL"), nullable=True
    )
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONBType, nullable=False, default=dict)
    pack_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("document_pack.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[DocumentJobStatus] = mapped_column(
        Enum(DocumentJobStatus, name="documentjobstatus"),
        default=DocumentJobStatus.QUEUED,
        nullable=False,
    )
    document_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("document.id", ondelete="SET NULL"), nullable=True
    )
    initiated_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("user.id", ondelete="RESTRICT"), nullable=False
    )
    last_error: Mapped[str | None] = mapped_column(String(255), nullable=True)
    queued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(tz=timezone.utc), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    document = relationship(
        "Document",
        back_populates="generation_jobs",
        foreign_keys=[document_id],
    )
    template = relationship(Template)
    company = relationship(Company)
    person = relationship(Person)
    initiator = relationship(User)
    pack: Mapped[DocumentPack | None] = relationship(DocumentPack)
    source_documents: Mapped[list["Document"]] = relationship(
        "Document", back_populates="job", foreign_keys=[Document.job_id]
    )
    requested_by = synonym("initiated_by")

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "idempotency_key",
            name="uq_document_job_tenant_idempotency",
        ),
        Index("ix_document_job_task_id", "task_id"),
        Index("ix_document_job_pack_id", "tenant_id", "pack_id"),
    )


class DocumentBatchStatus(str, enum.Enum):
    """Batch processing status."""

    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class DocumentBatchItemStatus(str, enum.Enum):
    """Per-row batch status."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class DocumentBatchRun(TenantBaseModel):
    """Tracks batch document generation."""

    __tablename__ = "document_batch_run"

    template_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("template.id", ondelete="RESTRICT"), nullable=False
    )
    template_version_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("templateversion.id", ondelete="RESTRICT"), nullable=False
    )
    company_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("company.id", ondelete="RESTRICT"), nullable=False
    )
    naming_pattern: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[DocumentBatchStatus] = mapped_column(
        native_enum(DocumentBatchStatus, name="documentbatchstatus"),
        nullable=False,
        default=DocumentBatchStatus.PENDING,
    )
    total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    succeeded: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_report: Mapped[dict[str, Any]] = mapped_column(JSONBType, nullable=False, default=dict)
    created_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("user.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(tz=timezone.utc),
        nullable=False,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    template = relationship(Template)
    template_version = relationship(TemplateVersion)
    company = relationship(Company)
    creator = relationship(User, foreign_keys=[created_by])
    items = relationship(
        "DocumentBatchItem",
        back_populates="batch",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (Index("ix_document_batch_run_tenant_created", "tenant_id", "created_at"),)


class DocumentBatchItem(TenantBaseModel):
    """Row-level batch item."""

    __tablename__ = "document_batch_item"

    batch_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("document_batch_run.id", ondelete="CASCADE"), nullable=False
    )
    row_index: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONBType, nullable=False, default=dict)
    person_id: Mapped[str | None] = mapped_column(String(36))
    output_name: Mapped[str | None] = mapped_column(String(255))
    pipeline_run_id: Mapped[str | None] = mapped_column(String(36))
    document_id: Mapped[str | None] = mapped_column(String(36))
    document_version_id: Mapped[str | None] = mapped_column(String(36))
    status: Mapped[DocumentBatchItemStatus] = mapped_column(
        native_enum(DocumentBatchItemStatus, name="documentbatchitemstatus"),
        nullable=False,
        default=DocumentBatchItemStatus.PENDING,
    )
    error: Mapped[str | None] = mapped_column(String(255))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    batch = relationship("DocumentBatchRun", back_populates="items")

    __table_args__ = (
        Index("ix_document_batch_item_batch", "batch_id"),
        Index("ix_document_batch_item_status", "tenant_id", "status"),
    )
