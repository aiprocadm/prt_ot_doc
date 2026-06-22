from __future__ import annotations

import enum
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.models.base import SoftDeleteMixin, TenantBaseModel, native_enum

JSONBType = JSONB().with_variant(JSON(), "sqlite")


class WorkflowDefinitionStatus(str, enum.Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class WorkflowInstanceStatus(str, enum.Enum):
    RUNNING = "running"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


class WorkflowTaskStatus(str, enum.Enum):
    OPEN = "open"
    COMPLETED = "completed"
    REASSIGNED = "reassigned"
    DELEGATED = "delegated"
    ESCALATED = "escalated"
    CANCELED = "canceled"


class WorkflowDefinition(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "workflow_definitions"

    code: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    current_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_workflow_definition_tenant_code"),
        Index("ix_workflow_definition_tenant_entity", "tenant_id", "entity_type"),
    )


class WorkflowDefinitionVersion(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "workflow_definition_versions"

    definition_id: Mapped[str] = mapped_column(
        ForeignKey("workflow_definitions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[WorkflowDefinitionStatus] = mapped_column(
        native_enum(WorkflowDefinitionStatus, name="workflowdefinitionstatus"),
        nullable=False,
        default=WorkflowDefinitionStatus.DRAFT,
    )
    graph_json: Mapped[dict[str, Any]] = mapped_column(JSONBType, nullable=False, default=dict)
    variables_schema: Mapped[dict[str, Any]] = mapped_column(
        JSONBType, nullable=False, default=dict
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "definition_id", "version_no", name="uq_workflow_definition_version"
        ),
        Index("ix_workflow_definition_version_tenant_status", "tenant_id", "status"),
    )


class WorkflowInstance(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "workflow_instances"

    definition_id: Mapped[str] = mapped_column(
        ForeignKey("workflow_definitions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    definition_version_id: Mapped[str] = mapped_column(
        ForeignKey("workflow_definition_versions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False)
    status: Mapped[WorkflowInstanceStatus] = mapped_column(
        native_enum(WorkflowInstanceStatus, name="workflowinstancestatus"),
        nullable=False,
        default=WorkflowInstanceStatus.RUNNING,
    )
    current_node_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    started_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    context_json: Mapped[dict[str, Any]] = mapped_column(JSONBType, nullable=False, default=dict)
    correlation_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    __table_args__ = (
        Index("ix_workflow_instance_tenant_entity", "tenant_id", "entity_type", "entity_id"),
        Index("ix_workflow_instance_tenant_status", "tenant_id", "status"),
    )


class WorkflowTask(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "workflow_tasks"

    instance_id: Mapped[str] = mapped_column(
        ForeignKey("workflow_instances.id", ondelete="CASCADE"), nullable=False, index=True
    )
    node_id: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    assignee_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    assignee_role_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[WorkflowTaskStatus] = mapped_column(
        native_enum(WorkflowTaskStatus, name="workflowtaskstatus"),
        nullable=False,
        default=WorkflowTaskStatus.OPEN,
    )
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delegated_from_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    task_payload: Mapped[dict[str, Any]] = mapped_column(JSONBType, nullable=False, default=dict)

    __table_args__ = (
        Index("ix_workflow_task_tenant_assignee_status", "tenant_id", "assignee_user_id", "status"),
        Index("ix_workflow_task_tenant_role_status", "tenant_id", "assignee_role_code", "status"),
    )


class WorkflowTimelineEvent(TenantBaseModel):
    __tablename__ = "workflow_timeline_events"

    instance_id: Mapped[str] = mapped_column(
        ForeignKey("workflow_instances.id", ondelete="CASCADE"), nullable=False, index=True
    )
    node_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONBType, nullable=False, default=dict)

    __table_args__ = (
        Index(
            "ix_workflow_timeline_tenant_instance_created", "tenant_id", "instance_id", "created_at"
        ),
    )
