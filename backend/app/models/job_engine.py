"""Job orchestration models for document pipeline engine."""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
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
    SENT = "sent"
    FAILED = "failed"


class DocumentJob(TenantBaseModel):
    __tablename__ = "document_jobs"

    status: Mapped[DocumentJobStatus] = mapped_column(
        String(16), nullable=False, default=DocumentJobStatus.QUEUED.value
    )
    pipeline_profile_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    template_code: Mapped[str] = mapped_column(String(255), nullable=False)
    template_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error_payload: Mapped[dict | None] = mapped_column(JSONBType, nullable=True)

    steps: Mapped[list["DocumentJobStep"]] = relationship(
        "DocumentJobStep", back_populates="job", cascade="all, delete-orphan"
    )
    artifacts: Mapped[list["DocumentArtifact"]] = relationship(
        "DocumentArtifact", back_populates="job", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_document_jobs_tenant_status_updated", "tenant_id", "status", "updated_at"),
        Index("ix_document_jobs_tenant_status", "tenant_id", "status"),
    )


class DocumentJobStep(TenantBaseModel):
    __tablename__ = "document_job_steps"

    job_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("document_jobs.id", ondelete="CASCADE"), nullable=False
    )
    step_code: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[JobStepStatus] = mapped_column(String(16), nullable=False, default=JobStepStatus.QUEUED.value)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error_payload: Mapped[dict | None] = mapped_column(JSONBType, nullable=True)

    job: Mapped[DocumentJob] = relationship("DocumentJob", back_populates="steps")

    __table_args__ = (UniqueConstraint("job_id", "step_code", name="uq_document_job_step"),)


class DocumentArtifact(TenantBaseModel):
    __tablename__ = "document_artifacts"

    job_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("document_jobs.id", ondelete="CASCADE"), nullable=False
    )
    step_code: Mapped[str] = mapped_column(String(64), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    file_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    meta: Mapped[dict] = mapped_column(JSONBType, nullable=False, default=dict)

    job: Mapped[DocumentJob] = relationship("DocumentJob", back_populates="artifacts")

    __table_args__ = (
        UniqueConstraint("job_id", "step_code", "kind", name="uq_document_artifact_step_kind"),
    )


class OutboxEvent(TenantBaseModel):
    __tablename__ = "outbox_events"

    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    event_id: Mapped[str] = mapped_column(String(36), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONBType, nullable=False, default=dict)
    status: Mapped[OutboxEventStatus] = mapped_column(String(16), nullable=False, default=OutboxEventStatus.PENDING.value)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint("tenant_id", "event_id", name="uq_outbox_event_tenant_event"),
        Index("ix_outbox_events_status", "status"),
    )

