"""Job orchestration models for document pipeline engine."""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.models.base import TenantBaseModel

JSONBType = JSONB().with_variant(JSON(), "sqlite")


class DocumentJobStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELED = "canceled"


class JobStepStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELED = "canceled"


class OutboxEventStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    SENT = "sent"
    FAILED = "failed"
    DEAD = "dead"


class DocumentJob(TenantBaseModel):
    __tablename__ = "document_jobs"

    kind: Mapped[str] = mapped_column(String(32), nullable=False, default="pipeline")
    status: Mapped[DocumentJobStatus] = mapped_column(String(16), nullable=False, default=DocumentJobStatus.QUEUED.value)
    pipeline_profile_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    profile_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    preset_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    input_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    idempotency_key_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    template_code: Mapped[str] = mapped_column(String(255), nullable=False)
    template_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    input: Mapped[dict | None] = mapped_column(JSONBType, nullable=True)
    output: Mapped[dict | None] = mapped_column(JSONBType, nullable=True)
    input_payload_json: Mapped[dict | None] = mapped_column(JSONBType, nullable=True)
    output_payload_json: Mapped[dict | None] = mapped_column(JSONBType, nullable=True)
    current_step_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    result_document_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    cancel_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error_payload: Mapped[dict | None] = mapped_column(JSONBType, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    steps: Mapped[list["DocumentJobStep"]] = relationship("DocumentJobStep", back_populates="job", cascade="all, delete-orphan")
    artifacts: Mapped[list["DocumentArtifact"]] = relationship("DocumentArtifact", back_populates="job", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_document_jobs_tenant_idempotency", "tenant_id", "idempotency_key"),
        Index("ix_document_jobs_tenant_status_updated", "tenant_id", "status", "updated_at"),
        Index("ix_document_jobs_tenant_status", "tenant_id", "status"),
        Index("ix_document_jobs_tenant_created", "tenant_id", "created_at"),
        Index("ix_document_jobs_tenant_updated", "tenant_id", "updated_at"),
    )


class DocumentJobStep(TenantBaseModel):
    __tablename__ = "document_job_steps"

    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("document_jobs.id", ondelete="CASCADE"), nullable=False)
    step_code: Mapped[str] = mapped_column(String(64), nullable=False)
    step_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    step_order: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[JobStepStatus] = mapped_column(String(16), nullable=False, default=JobStepStatus.QUEUED.value)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    inputs_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    input_ref: Mapped[dict | None] = mapped_column(JSONBType, nullable=True)
    output_ref: Mapped[dict | None] = mapped_column(JSONBType, nullable=True)
    input: Mapped[dict | None] = mapped_column(JSONBType, nullable=True)
    output: Mapped[dict | None] = mapped_column(JSONBType, nullable=True)
    logs_file_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    logs_uri: Mapped[str | None] = mapped_column(String(512), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error_payload: Mapped[dict | None] = mapped_column(JSONBType, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    job: Mapped[DocumentJob] = relationship("DocumentJob", back_populates="steps")

    __table_args__ = (
        UniqueConstraint("job_id", "step_code", name="uq_document_job_step"),
        Index("ix_job_steps_tenant_job", "tenant_id", "job_id"),
        Index("ix_job_steps_tenant_job_order", "tenant_id", "job_id", "step_order"),
    )


class DocumentArtifact(TenantBaseModel):
    __tablename__ = "document_artifacts"

    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("document_jobs.id", ondelete="CASCADE"), nullable=False)
    step_code: Mapped[str] = mapped_column(String(64), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    file_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    meta: Mapped[dict] = mapped_column(JSONBType, nullable=False, default=dict)

    job: Mapped[DocumentJob] = relationship("DocumentJob", back_populates="artifacts")

    __table_args__ = (UniqueConstraint("job_id", "step_code", "kind", name="uq_document_artifact_step_kind"),)


class DocumentJobLog(TenantBaseModel):
    __tablename__ = "job_logs"

    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("document_jobs.id", ondelete="CASCADE"), nullable=False)
    step_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    level: Mapped[str] = mapped_column(String(16), nullable=False, default="info")
    message: Mapped[str] = mapped_column(String(1024), nullable=False)
    meta_json: Mapped[dict | None] = mapped_column(JSONBType, nullable=True)

    __table_args__ = (Index("ix_job_logs_tenant_job_created", "tenant_id", "job_id", "created_at"),)


class OutboxEvent(TenantBaseModel):
    __tablename__ = "outbox_events"

    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    event_id: Mapped[str] = mapped_column(String(36), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONBType, nullable=False, default=dict)
    status: Mapped[OutboxEventStatus] = mapped_column(String(16), nullable=False, default=OutboxEventStatus.PENDING.value)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "event_id", name="uq_outbox_event_tenant_event"),
        Index("ix_outbox_events_status_next_attempt", "status", "next_attempt_at"),
        Index("ix_outbox_events_tenant_created", "tenant_id", "created_at"),
    )
