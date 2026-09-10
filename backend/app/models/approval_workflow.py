from __future__ import annotations

import enum
from datetime import datetime
from typing import Any

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

from app.models.base import SoftDeleteMixin, TenantBaseModel, native_enum


class ApprovalRequestStatus(str, enum.Enum):
    DRAFT = "draft"
    RUNNING = "running"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELED = "canceled"


class ApprovalDecisionType(str, enum.Enum):
    APPROVE = "approve"
    REJECT = "reject"
    DELEGATE = "delegate"


class SignatureType(str, enum.Enum):
    KEP = "KEP"
    UNEP = "UNEP"
    INTERNAL = "INTERNAL"


class EdoDirection(str, enum.Enum):
    OUTGOING = "outgoing"
    INCOMING = "incoming"


class EdoStatus(str, enum.Enum):
    QUEUED = "queued"
    SENT = "sent"
    DELIVERED = "delivered"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    FAILED = "failed"


class ApprovalRouteAppliesTo(str, enum.Enum):
    DOCUMENT = "document"
    PACK = "pack"
    BOTH = "both"


class ApprovalRouteStatus(str, enum.Enum):
    ACTIVE = "active"
    DRAFT = "draft"
    ARCHIVED = "archived"


class ApprovalStepType(str, enum.Enum):
    APPROVE = "approve"
    SIGN = "sign"
    REVIEW = "review"


class ApprovalInstanceStatus(str, enum.Enum):
    DRAFT = "draft"
    RUNNING = "running"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELED = "canceled"
    EXPIRED = "expired"


class ApprovalInstanceStepStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    SKIPPED = "skipped"
    EXPIRED = "expired"
    DELEGATED = "delegated"


class SignatureProviderStatus(str, enum.Enum):
    PENDING = "pending"
    SIGNED = "signed"
    FAILED = "failed"
    CANCELED = "canceled"
    VERIFYING = "verifying"
    VERIFIED = "verified"


class EdoMessageStatus(str, enum.Enum):
    DRAFT = "draft"
    QUEUED = "queued"
    SENT = "sent"
    DELIVERED = "delivered"
    VIEWED = "viewed"
    SIGNED = "signed"
    COMPLETED = "completed"
    REJECTED = "rejected"
    FAILED = "failed"


class ApprovalRoute(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "approval_routes"

    code: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    applies_to: Mapped[ApprovalRouteAppliesTo] = mapped_column(
        Enum(ApprovalRouteAppliesTo), nullable=False, default=ApprovalRouteAppliesTo.DOCUMENT
    )
    conditions_json: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[ApprovalRouteStatus] = mapped_column(
        Enum(ApprovalRouteStatus), nullable=False, default=ApprovalRouteStatus.DRAFT
    )
    rules_json: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    conditions: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )
    steps: Mapped[list[dict[str, Any]]] = mapped_column(
        MutableList.as_mutable(JSON), nullable=False, default=list
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("tenant_id", "code", "version", name="uq_approval_route_code_version"),
        Index("ix_approval_routes_code", "tenant_id", "code"),
    )


class ApprovalRequest(TenantBaseModel):
    __tablename__ = "approval_requests"

    document_version_id: Mapped[str] = mapped_column(
        ForeignKey("documentversion.id"), nullable=False, index=True
    )
    route_id: Mapped[str] = mapped_column(
        ForeignKey("approval_routes.id"), nullable=False, index=True
    )
    status: Mapped[ApprovalRequestStatus] = mapped_column(
        native_enum(ApprovalRequestStatus), nullable=False, default=ApprovalRequestStatus.DRAFT
    )
    current_step_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("user.id"), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    route: Mapped[ApprovalRoute] = relationship("ApprovalRoute")

    __table_args__ = (
        Index("ix_approval_requests_status", "tenant_id", "status"),
        Index("ix_approval_requests_created", "tenant_id", "created_at"),
    )


class ApprovalDecision(TenantBaseModel):
    __tablename__ = "approval_decisions"

    request_id: Mapped[str | None] = mapped_column(
        ForeignKey("approval_requests.id"), nullable=True, index=True
    )
    approval_instance_id: Mapped[str | None] = mapped_column(
        ForeignKey("approval_instances.id"), nullable=True, index=True
    )
    approval_instance_step_id: Mapped[str | None] = mapped_column(
        ForeignKey("approval_instance_steps.id"), nullable=True, index=True
    )
    step_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actor_user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text)
    payload_json: Mapped[dict[str, Any] | None] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=True
    )
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)

    request: Mapped[ApprovalRequest | None] = relationship("ApprovalRequest", backref="decisions")


class EdoMessage(TenantBaseModel):
    __tablename__ = "edo_messages"

    direction: Mapped[EdoDirection] = mapped_column(native_enum(EdoDirection), nullable=False)
    document_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("documentversion.id"), nullable=True, index=True
    )
    provider_code: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    operator_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    message_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(255), index=True)
    external_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    external_thread_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    roaming_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_status_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    request_payload_json: Mapped[dict[str, Any] | None] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=True
    )
    response_payload_json: Mapped[dict[str, Any] | None] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=True
    )
    protocol_file_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=EdoMessageStatus.DRAFT.value
    )
    payload_json: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )

    __table_args__ = (
        Index("ix_edo_messages_created", "tenant_id", "created_at"),
        Index("ix_edo_messages_provider_external", "tenant_id", "provider_code", "external_id"),
    )


class EdoStatusHistory(TenantBaseModel):
    __tablename__ = "edo_status_history"

    edo_message_id: Mapped[str] = mapped_column(
        ForeignKey("edo_messages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[EdoStatus] = mapped_column(native_enum(EdoStatus), nullable=False)
    raw_payload_json: Mapped[dict[str, Any] | None] = mapped_column(MutableDict.as_mutable(JSON))
