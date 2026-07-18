"""Package / pack-run / document-pack / pipeline / client-portal ORM models — extracted from models.py (ARCH-2 decomposition).

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
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.ext.mutable import MutableDict, MutableList
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import (
    SoftDeleteMixin,
    TenantBaseModel,
    native_enum,
)

if TYPE_CHECKING:  # pragma: no cover - type-checker only; SA resolves via registry
    from app.models.models import (
        Template,
    )
    from app.models.templates import TemplateVersion


class PackageEntityStatus(str, enum.Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class PackageSourceType(str, enum.Enum):
    CSV = "csv"
    XLSX = "xlsx"
    JSON = "json"
    MIXED = "mixed"


class ReplaceMode(str, enum.Enum):
    NONE = "none"
    PREVIEW = "preview"
    APPLY = "apply"


class OutputFormat(str, enum.Enum):
    DOCX = "docx"
    PDF = "pdf"
    BOTH = "both"


class PackRunLifecycleStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELED = "canceled"
    PARTIAL_SUCCESS = "partial_success"


class PackRunItemStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class PackLogLevel(str, enum.Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class PackageProfileConfig(TenantBaseModel):
    __tablename__ = "package_profiles_v2"

    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    pipeline_steps_json: Mapped[list[dict[str, Any]]] = mapped_column(
        MutableList.as_mutable(JSON), nullable=False, default=list
    )
    concurrency_limit: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[PackageEntityStatus] = mapped_column(
        native_enum(PackageEntityStatus, name="package_entity_status"),
        nullable=False,
        default=PackageEntityStatus.DRAFT,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_package_profiles_v2_tenant_code"),
        Index("ix_package_profiles_v2_tenant_status_updated", "tenant_id", "status", "updated_at"),
    )


class PackagePresetConfig(TenantBaseModel):
    __tablename__ = "package_presets_v2"

    code: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    package_profile_id: Mapped[str] = mapped_column(
        ForeignKey("package_profiles_v2.id"), nullable=False, index=True
    )
    naming_rule: Mapped[str] = mapped_column(String(512), nullable=False)
    source_type: Mapped[PackageSourceType] = mapped_column(
        native_enum(PackageSourceType, name="package_source_type"),
        nullable=False,
        default=PackageSourceType.CSV,
    )
    mapping_json: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )
    options_json: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )
    status: Mapped[PackageEntityStatus] = mapped_column(
        native_enum(PackageEntityStatus, name="package_preset_status"),
        nullable=False,
        default=PackageEntityStatus.DRAFT,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    profile: Mapped[PackageProfileConfig] = relationship(backref="presets_v2")

    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_package_presets_v2_tenant_code"),
        Index("ix_package_presets_v2_tenant_status_updated", "tenant_id", "status", "updated_at"),
    )


class PackagePresetItem(TenantBaseModel):
    __tablename__ = "package_preset_items"

    package_preset_id: Mapped[str] = mapped_column(
        ForeignKey("package_presets_v2.id"), nullable=False, index=True
    )
    order_no: Mapped[int] = mapped_column(Integer, nullable=False)
    template_id: Mapped[str | None] = mapped_column(
        ForeignKey("template.id"), nullable=True, index=True
    )
    template_version_id: Mapped[str] = mapped_column(
        ForeignKey("templateversion.id"), nullable=False, index=True
    )
    header_preset_json: Mapped[dict[str, Any] | None] = mapped_column(MutableDict.as_mutable(JSON))
    replace_mode: Mapped[ReplaceMode] = mapped_column(
        native_enum(ReplaceMode, name="replace_mode"), nullable=False, default=ReplaceMode.NONE
    )
    replace_map_json: Mapped[dict[str, Any] | None] = mapped_column(MutableDict.as_mutable(JSON))
    output_format: Mapped[OutputFormat] = mapped_column(
        native_enum(OutputFormat, name="package_output_format"),
        nullable=False,
        default=OutputFormat.BOTH,
    )
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    conditions_json: Mapped[dict[str, Any] | None] = mapped_column(MutableDict.as_mutable(JSON))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    preset: Mapped[PackagePresetConfig] = relationship(backref="items")
    template: Mapped[Template | None] = relationship("Template", backref="package_preset_items")
    template_version: Mapped[TemplateVersion] = relationship(
        "TemplateVersion", backref="package_preset_items_v2"
    )

    __table_args__ = (
        UniqueConstraint("package_preset_id", "order_no", name="uq_package_preset_items_order"),
        Index("ix_package_preset_items_order", "package_preset_id", "order_no"),
    )


class PackRun(TenantBaseModel):
    __tablename__ = "pack_runs"

    package_preset_id: Mapped[str] = mapped_column(
        ForeignKey("package_presets_v2.id"), nullable=False, index=True
    )
    package_profile_id: Mapped[str] = mapped_column(
        ForeignKey("package_profiles_v2.id"), nullable=False, index=True
    )
    source_file_id: Mapped[str | None] = mapped_column(ForeignKey("file.id"), nullable=True)
    source_type: Mapped[PackageSourceType] = mapped_column(
        native_enum(PackageSourceType, name="pack_run_source_type"), nullable=False
    )
    source_rows_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    selected_rows_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[PackRunLifecycleStatus] = mapped_column(
        native_enum(PackRunLifecycleStatus, name="pack_run_lifecycle_status"),
        nullable=False,
        default=PackRunLifecycleStatus.QUEUED,
    )
    result_zip_file_id: Mapped[str | None] = mapped_column(ForeignKey("file.id"), nullable=True)
    stats_json: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    request_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    approval_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    signature_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    edo_status: Mapped[str | None] = mapped_column(String(32), nullable=True)

    __table_args__ = (
        Index("ix_pack_runs_status_created", "tenant_id", "status", "created_at"),
        Index("ix_pack_runs_tenant_status_updated", "tenant_id", "status", "updated_at"),
        UniqueConstraint(
            "tenant_id", "idempotency_key", "request_hash", name="uq_pack_runs_idempotency"
        ),
    )


class PackRunItem(TenantBaseModel):
    __tablename__ = "pack_run_items"

    pack_run_id: Mapped[str] = mapped_column(ForeignKey("pack_runs.id"), nullable=False, index=True)
    row_no: Mapped[int] = mapped_column(Integer, nullable=False)
    source_record_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[PackRunItemStatus] = mapped_column(
        native_enum(PackRunItemStatus, name="pack_run_item_status"),
        nullable=False,
        default=PackRunItemStatus.QUEUED,
    )
    document_job_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    output_docx_file_id: Mapped[str | None] = mapped_column(ForeignKey("file.id"), nullable=True)
    output_pdf_file_id: Mapped[str | None] = mapped_column(ForeignKey("file.id"), nullable=True)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error_payload: Mapped[dict[str, Any] | None] = mapped_column(MutableDict.as_mutable(JSON))

    __table_args__ = (Index("ix_pack_run_items_run_status", "pack_run_id", "status"),)


class PackRunLog(TenantBaseModel):
    __tablename__ = "pack_run_logs"

    pack_run_id: Mapped[str] = mapped_column(ForeignKey("pack_runs.id"), nullable=False, index=True)
    level: Mapped[PackLogLevel] = mapped_column(
        native_enum(PackLogLevel, name="pack_log_level"), nullable=False
    )
    step: Mapped[str | None] = mapped_column(String(64))
    message: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any] | None] = mapped_column(MutableDict.as_mutable(JSON))


class PackageProfile(TenantBaseModel):
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1024))
    config: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )

    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_package_profile_name"),)


class PackagePreset(TenantBaseModel):
    profile_id: Mapped[str] = mapped_column(
        ForeignKey("packageprofile.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )

    profile: Mapped[PackageProfile] = relationship(backref="presets")


class DocumentPackModule(str, enum.Enum):
    """High-level grouping for document packs."""

    OT = "ot"
    FIRE_SAFETY = "fire_safety"
    HEALTH = "health"
    CUSTOM = "custom"


class DocumentPackScenario(str, enum.Enum):
    """Execution scenario describing how a pack runs."""

    DOCUMENT_BATCH = "document_batch"
    REPORT = "report"
    WORKFLOW = "workflow"


class DocumentPack(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "document_pack"

    code: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # values_callable: PG enum ``documentpackmodule`` was created with
    # lowercase values ("ot", "fire_safety", ...) in migration
    # 8d2c1a6c5e24:43-66. SQLAlchemy's default sends the Python member
    # *name* ("OT") for INSERT, which PG rejects. Same root cause and
    # migration as ``Person.employment_status`` (iter-17 RB-002c).
    module: Mapped[DocumentPackModule] = mapped_column(
        Enum(
            DocumentPackModule,
            name="documentpackmodule",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=DocumentPackModule.OT,
    )
    # Same lowercase-PG-enum drift as ``module`` above. PG type
    # ``documentpackscenario`` accepts ("document_batch", "report",
    # "workflow"); Python member names are uppercase.
    scenario_type: Mapped[DocumentPackScenario] = mapped_column(
        Enum(
            DocumentPackScenario,
            name="documentpackscenario",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=DocumentPackScenario.DOCUMENT_BATCH,
    )

    items: Mapped[list["DocumentPackItem"]] = relationship(
        back_populates="pack",
        cascade="all, delete-orphan",
        order_by="DocumentPackItem.order",
        lazy="selectin",
    )

    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_document_pack_code"),)


class DocumentPackItem(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "document_pack_item"

    pack_id: Mapped[str] = mapped_column(ForeignKey("document_pack.id"), nullable=False, index=True)
    template_id: Mapped[str] = mapped_column(ForeignKey("template.id"), nullable=False, index=True)
    template_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("templateversion.id"), nullable=True, index=True
    )
    order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    condition: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )

    pack: Mapped[DocumentPack] = relationship(back_populates="items")
    template: Mapped[Template] = relationship(backref="document_pack_items", lazy="selectin")
    template_version: Mapped[TemplateVersion | None] = relationship(
        "TemplateVersion", backref="document_pack_items", lazy="selectin"
    )


class PipelineRunStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"


class PipelineRun(TenantBaseModel):
    __tablename__ = "pipeline_runs"

    template_id: Mapped[str] = mapped_column(ForeignKey("template.id"), nullable=False, index=True)
    template_version_id: Mapped[str] = mapped_column(
        ForeignKey("templateversion.id"), nullable=False, index=True
    )
    status: Mapped[PipelineRunStatus] = mapped_column(
        Enum(PipelineRunStatus), nullable=False, default=PipelineRunStatus.QUEUED
    )
    context: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )
    # MutableDict so top-level in-place edits (outputs["pdf"]=..., result_metadata[...])
    # are flagged dirty even without a fresh reassignment. This is the column that
    # produced the _record_stage data-loss bug; see tests/test_no_inplace_json_mutation.py.
    # NOTE: only TOP-LEVEL keys are tracked — nested edits (outputs["stages"][k]=...)
    # still require reassigning a fresh object.
    outputs: Mapped[dict[str, Any] | None] = mapped_column(MutableDict.as_mutable(JSON))
    result_metadata: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )
    docx_storage_key: Mapped[str | None] = mapped_column(String(512))
    pdf_storage_key: Mapped[str | None] = mapped_column(String(512))
    result_s3_key: Mapped[str | None] = mapped_column(String(512))
    error: Mapped[str | None] = mapped_column(String(255))
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    template: Mapped[Template] = relationship(backref="pipeline_runs")
    template_version: Mapped[TemplateVersion] = relationship(backref="pipeline_runs")

    __table_args__ = (
        Index(
            "ix_pipeline_runs_tenant_idempotency",
            "tenant_id",
            "idempotency_key",
            unique=True,
        ),
    )


class PackageRunStatus(str, enum.Enum):
    DRAFT = "draft"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELED = "canceled"


class PackageRequirementType(str, enum.Enum):
    FILE = "file"
    TEXT = "text"
    TABLE = "table"


class PackageRequirementStatus(str, enum.Enum):
    MISSING = "missing"
    PROVIDED = "provided"
    APPROVED = "approved"
    REJECTED = "rejected"


class ClientRequestTicketStatus(str, enum.Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"


class ClientPackagePreset(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "package_presets"

    code: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    steps_json: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )
    required_inputs_json: Mapped[list[dict[str, Any]]] = mapped_column(
        MutableList.as_mutable(JSON), nullable=False, default=list
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_package_presets_code"),
        Index("ix_package_presets_code", "tenant_id", "code"),
    )


class ClientPackageRun(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "package_runs"

    preset_id: Mapped[str] = mapped_column(
        ForeignKey("package_presets.id"), nullable=False, index=True
    )
    initiated_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("user.id"), nullable=True, index=True
    )
    client_company_id: Mapped[str | None] = mapped_column(
        ForeignKey("company.id"), nullable=True, index=True
    )
    status: Mapped[PackageRunStatus] = mapped_column(
        native_enum(PackageRunStatus), nullable=False, default=PackageRunStatus.DRAFT
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    output_zip_s3_key: Mapped[str | None] = mapped_column(String(512))
    output_pdf_s3_key: Mapped[str | None] = mapped_column(String(512))
    qc_report_json: Mapped[dict[str, Any] | None] = mapped_column(MutableDict.as_mutable(JSON))
    error_payload_json: Mapped[dict[str, Any] | None] = mapped_column(MutableDict.as_mutable(JSON))

    preset: Mapped[ClientPackagePreset] = relationship(backref="runs")

    __table_args__ = (Index("ix_package_runs_status_updated", "tenant_id", "status", "updated_at"),)


class PackageRequirement(TenantBaseModel):
    __tablename__ = "package_requirements"

    package_run_id: Mapped[str] = mapped_column(
        ForeignKey("package_runs.id"), nullable=False, index=True
    )
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[PackageRequirementType] = mapped_column(
        native_enum(PackageRequirementType), nullable=False, default=PackageRequirementType.FILE
    )
    status: Mapped[PackageRequirementStatus] = mapped_column(
        native_enum(PackageRequirementStatus),
        nullable=False,
        default=PackageRequirementStatus.MISSING,
    )
    payload_json: Mapped[dict[str, Any] | None] = mapped_column(MutableDict.as_mutable(JSON))


class ClientPortalToken(TenantBaseModel):
    __tablename__ = "client_portal_tokens"

    token_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    package_run_id: Mapped[str] = mapped_column(
        ForeignKey("package_runs.id"), nullable=False, index=True
    )
    scope_json: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_client_portal_tokens_expires_hash", "tenant_id", "expires_at", "token_hash"),
    )


class ClientRequestTicket(TenantBaseModel):
    __tablename__ = "client_request_tickets"

    package_run_id: Mapped[str] = mapped_column(
        ForeignKey("package_runs.id"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[ClientRequestTicketStatus] = mapped_column(
        native_enum(ClientRequestTicketStatus),
        nullable=False,
        default=ClientRequestTicketStatus.OPEN,
    )
    created_by: Mapped[str | None] = mapped_column(String(128))


class PackageEvent(TenantBaseModel):
    __tablename__ = "package_events"

    package_run_id: Mapped[str] = mapped_column(
        ForeignKey("package_runs.id"), nullable=False, index=True
    )
    type: Mapped[str] = mapped_column(String(128), nullable=False)
    payload_json: Mapped[dict[str, Any] | None] = mapped_column(MutableDict.as_mutable(JSON))
