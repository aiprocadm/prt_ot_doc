"""Approval / EDO / signature / outbox / webhook runtime ORM models — extracted
from models.py (ARCH-2 decomposition).

Pure move of class definitions: same registry, identical tables. Public import
paths ``from app.models.models import X`` / ``from app.models import X`` are
preserved by re-exports in models.py / __init__.py. This block binds a few
approval-workflow enums at RUNTIME (``Enum(ApprovalStepType)`` etc.), so those
are imported normally (not under TYPE_CHECKING). Other external classes in
``Mapped[...]`` annotations are resolved by SQLAlchemy's class registry.
"""

from __future__ import annotations

import enum
from datetime import datetime, timezone
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
from sqlalchemy.orm import Mapped, mapped_column

from app.models.approval_workflow import (
    ApprovalInstanceStatus,
    ApprovalInstanceStepStatus,
    ApprovalStepType,
    SignatureProviderStatus,
)
from app.models.base import (
    SoftDeleteMixin,
    TenantBaseModel,
    VersionedMixin,
    native_enum,
)

if TYPE_CHECKING:  # pragma: no cover - type-checker only; SA resolves via registry
    pass


class OutboxStatus(str, enum.Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    SENT = "SENT"
    FAILED = "FAILED"
    DEAD = "DEAD"


class ApprovalProcessStatus(str, enum.Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELED = "canceled"
    EXPIRED = "expired"


class ApprovalTaskStatus(str, enum.Enum):
    OPEN = "open"
    DONE = "done"
    CANCELED = "canceled"
    EXPIRED = "expired"


class ApprovalProcess(TenantBaseModel):
    __tablename__ = "approval_processes"

    object_type: Mapped[str] = mapped_column(String(64), nullable=False)
    object_id: Mapped[str] = mapped_column(String(36), nullable=False)
    route_id: Mapped[str] = mapped_column(
        ForeignKey("approval_routes.id"), nullable=False, index=True
    )
    status: Mapped[ApprovalProcessStatus] = mapped_column(
        native_enum(ApprovalProcessStatus), nullable=False, default=ApprovalProcessStatus.PENDING
    )
    current_step: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[str | None] = mapped_column(ForeignKey("user.id"), nullable=True, index=True)

    __table_args__ = (
        Index("ix_approval_processes_status", "tenant_id", "status"),
        Index("ix_approval_processes_object", "tenant_id", "object_type", "object_id"),
    )


class ApprovalTask(TenantBaseModel):
    __tablename__ = "approval_tasks"

    process_id: Mapped[str] = mapped_column(
        ForeignKey("approval_processes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    step_no: Mapped[int] = mapped_column(Integer, nullable=False)
    assignee_type: Mapped[str] = mapped_column(String(16), nullable=False)
    assignee_id: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[ApprovalTaskStatus] = mapped_column(
        native_enum(ApprovalTaskStatus), nullable=False, default=ApprovalTaskStatus.OPEN
    )
    decision: Mapped[str | None] = mapped_column(String(16), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    delegated_from: Mapped[str | None] = mapped_column(String(36), nullable=True)

    __table_args__ = (
        Index("ix_approval_tasks_status", "tenant_id", "status"),
        Index("ix_approval_tasks_assignee", "tenant_id", "assignee_type", "assignee_id"),
    )


class ApprovalDecisionLog(TenantBaseModel):
    __tablename__ = "approval_decision_logs"

    process_id: Mapped[str] = mapped_column(
        ForeignKey("approval_processes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    task_id: Mapped[str | None] = mapped_column(
        ForeignKey("approval_tasks.id", ondelete="SET NULL"), nullable=True, index=True
    )
    step_no: Mapped[int] = mapped_column(Integer, nullable=False)
    actor_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text)
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(512))


class ApprovalRouteStep(TenantBaseModel, SoftDeleteMixin, VersionedMixin):
    __tablename__ = "approval_route_steps"

    approval_route_id: Mapped[str] = mapped_column(
        ForeignKey("approval_routes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    order_no: Mapped[int] = mapped_column(Integer, nullable=False)
    step_type: Mapped[ApprovalStepType] = mapped_column(
        Enum(ApprovalStepType), nullable=False, default=ApprovalStepType.APPROVE
    )
    role_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    can_delegate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    deadline_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    escalation_role_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    escalation_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    conditions_json: Mapped[dict[str, Any] | None] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("approval_route_id", "order_no", name="uq_approval_route_steps_order"),
        Index("ix_approval_route_steps_route_order", "approval_route_id", "order_no"),
    )


class ApprovalInstance(TenantBaseModel, SoftDeleteMixin, VersionedMixin):
    __tablename__ = "approval_instances"

    entity_type: Mapped[str] = mapped_column(String(16), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    approval_route_id: Mapped[str] = mapped_column(
        ForeignKey("approval_routes.id"), nullable=False, index=True
    )
    status: Mapped[ApprovalInstanceStatus] = mapped_column(
        Enum(ApprovalInstanceStatus), nullable=False, default=ApprovalInstanceStatus.DRAFT
    )
    started_by: Mapped[str] = mapped_column(String(36), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    current_step_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_approval_instances_entity", "tenant_id", "entity_type", "entity_id"),
        Index("ix_approval_instances_status", "tenant_id", "status"),
    )


class ApprovalInstanceStep(TenantBaseModel):
    __tablename__ = "approval_instance_steps"

    approval_instance_id: Mapped[str] = mapped_column(
        ForeignKey("approval_instances.id", ondelete="CASCADE"), nullable=False, index=True
    )
    route_step_id: Mapped[str] = mapped_column(
        ForeignKey("approval_route_steps.id"), nullable=False, index=True
    )
    order_no: Mapped[int] = mapped_column(Integer, nullable=False)
    assignee_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    assignee_role_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    delegated_from_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[ApprovalInstanceStepStatus] = mapped_column(
        Enum(ApprovalInstanceStepStatus), nullable=False, default=ApprovalInstanceStepStatus.PENDING
    )
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload_json: Mapped[dict[str, Any] | None] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=True
    )

    __table_args__ = (
        Index("ix_approval_instance_steps_lookup", "approval_instance_id", "status", "order_no"),
    )


class EdoStatusEvent(TenantBaseModel):
    __tablename__ = "edo_status_events"

    edo_message_id: Mapped[str] = mapped_column(
        ForeignKey("edo_messages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    external_event_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    payload_json: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(tz=timezone.utc)
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dedupe_key: Mapped[str | None] = mapped_column(String(255), nullable=True)

    __table_args__ = (
        Index("ix_edo_status_events_message_received", "edo_message_id", "received_at"),
    )


class EdoWebhookInbox(TenantBaseModel):
    __tablename__ = "edo_webhook_inbox"

    operator_code: Mapped[str] = mapped_column(String(64), nullable=False)
    external_event_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    dedupe_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    headers_json: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )
    payload_json: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="received")
    error_text: Mapped[str | None] = mapped_column(Text, nullable=True)


class SignatureRequestStatus(str, enum.Enum):
    CREATED = "created"
    REQUESTED = "requested"
    SIGNED = "signed"
    FAILED = "failed"
    AWAITING_CODE = "awaiting_code"
    DECLINED = "declined"
    EXPIRED = "expired"


class SignatureRequest(TenantBaseModel):
    __tablename__ = "signature_requests"

    object_type: Mapped[str] = mapped_column(String(64), nullable=False)
    object_id: Mapped[str] = mapped_column(String(36), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    requested_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    approval_instance_id: Mapped[str | None] = mapped_column(
        ForeignKey("approval_instances.id"), nullable=True, index=True
    )
    signature_type: Mapped[str] = mapped_column(String(16), nullable=False, default="kep")
    provider_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=SignatureProviderStatus.PENDING.value
    )
    external_request_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    certificate_thumbprint: Mapped[str | None] = mapped_column(String(255), nullable=True)
    signer_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verification_result_json: Mapped[dict[str, Any] | None] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=True
    )
    payload_json: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )
    result_json: Mapped[dict[str, Any] | None] = mapped_column(MutableDict.as_mutable(JSON))

    # --- PEP (простая электронная подпись, ed01) ---
    # Plain string — no FK (user ids come from external auth; pattern follows requested_by).
    signer_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    signer_person_id: Mapped[str | None] = mapped_column(
        ForeignKey("person.id", ondelete="SET NULL"), nullable=True, index=True
    )
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    purpose: Mapped[str | None] = mapped_column(String(32), nullable=True)
    confirm_code_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    confirm_code_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    confirm_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    __table_args__ = (
        Index("ix_signature_requests_status", "tenant_id", "status"),
        Index("ix_signature_requests_object", "tenant_id", "object_type", "object_id"),
        Index(
            "ix_signature_requests_entity_status", "tenant_id", "object_type", "object_id", "status"
        ),
    )


class Outbox(TenantBaseModel):
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    destination: Mapped[str] = mapped_column(String(512), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )
    headers: Mapped[dict[str, Any] | None] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=True
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[OutboxStatus] = mapped_column(
        Enum(OutboxStatus),
        nullable=False,
        default=OutboxStatus.PENDING,
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[dict[str, Any] | None] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=True
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_outbox_status_next_attempt", "status", "next_attempt_at"),
        Index("ix_outbox_event_type", "event_type"),
        Index("ix_outbox_idempotency_key", "idempotency_key"),
        UniqueConstraint(
            "tenant_id",
            "destination",
            "idempotency_key",
            name="uq_outbox_idempotency",
        ),
    )


class WebhookDelivery(TenantBaseModel):
    __tablename__ = "webhook_deliveries"

    endpoint_id: Mapped[str] = mapped_column(String(36), nullable=False)
    event_id: Mapped[str] = mapped_column(String(64), nullable=False)
    # Explicit link back to the source Outbox row so :retry can re-drive delivery
    # (the OutboxProcessor is the actual delivery engine; this table is a mirror).
    outbox_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    request_headers: Mapped[dict[str, Any] | None] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=True
    )
    response_headers: Mapped[dict[str, Any] | None] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=True
    )
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_status_code: Mapped[int | None] = mapped_column(Integer)
    last_response_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_error: Mapped[dict[str, Any] | None] = mapped_column(MutableDict.as_mutable(JSON))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("endpoint_id", "event_id", name="uq_webhook_delivery_endpoint_event"),
        Index("ix_webhook_delivery_lookup", "tenant_id", "endpoint_id", "event_id"),
    )


class WebhookEndpoint(TenantBaseModel):
    __tablename__ = "webhook_endpoints"

    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    secret: Mapped[str | None] = mapped_column(String(512), nullable=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    subscribed_events: Mapped[list[str]] = mapped_column(
        MutableList.as_mutable(JSON), nullable=False, default=list
    )
    timeout_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=5000)
    headers: Mapped[dict[str, Any] | None] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=True
    )

    __table_args__ = (Index("ix_webhook_endpoint_tenant_enabled", "tenant_id", "is_enabled"),)
