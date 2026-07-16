"""Notification, reminder rule, and calendar task models."""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Index, String, Text, UniqueConstraint, text
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import SoftDeleteMixin, TenantBaseModel, native_enum


class NotificationChannel(str, enum.Enum):
    EMAIL = "email"
    TELEGRAM = "telegram"
    INAPP = "inapp"
    WEBHOOK = "webhook"


class NotificationStatus(str, enum.Enum):
    QUEUED = "queued"
    SENT = "sent"
    FAILED = "failed"
    CANCELED = "canceled"
    READ = "read"


class NotificationPriority(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class NotificationType(str, enum.Enum):
    JOB_STATUS_CHANGED = "JobStatusChanged"
    DOCUMENT_GENERATED = "DocumentGenerated"
    DOCUMENT_EXPORTED = "DocumentExported"
    DOCUMENT_SIGNED = "DocumentSigned"
    TRAINING_DUE_SOON = "TrainingDueSoon"
    TRAINING_OVERDUE = "TrainingOverdue"
    TRAINING_COMPLETED = "TrainingCompleted"
    PPE_EXPIRY_SOON = "PPEExpirySoon"
    PPE_ISSUE_CREATED = "PPEIssueCreated"
    MEDICAL_DUE_SOON = "MedicalDueSoon"
    PERMIT_EXPIRY_SOON = "PermitExpirySoon"
    INSPECTION_PLANNED = "InspectionPlanned"
    INSPECTION_OVERDUE = "InspectionOverdue"
    INCIDENT_ASSIGNED = "IncidentAssigned"
    CA_DUE_SOON = "CADueSoon"
    APPROVAL_DEADLINE = "ApprovalDeadline"
    MEDICAL_OVERDUE = "MedicalOverdue"
    PPE_OVERDUE = "PPEOverdue"
    INCIDENT_CREATED = "IncidentCreated"
    INSPECTION_CREATED = "InspectionCreated"
    PRESCRIPTION_OVERDUE = "PrescriptionOverdue"
    PACKAGE_RUN_COMPLETED = "PackageRunCompleted"
    PACKAGE_RUN_FAILED = "PackageRunFailed"
    INTEGRATION_ERROR = "IntegrationError"
    EDO_STATUS_CHANGED = "EdoStatusChanged"
    BILLING_LIMIT_WARNING = "BillingLimitWarning"
    AUTOMATION_RULE = "AutomationRule"


class NotificationTemplate(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "notification_templates"

    code: Mapped[str] = mapped_column(String(128), nullable=False)
    channel: Mapped[NotificationChannel] = mapped_column(
        native_enum(NotificationChannel, name="notificationtemplatechannel"), nullable=False
    )
    type: Mapped[NotificationType] = mapped_column(
        native_enum(NotificationType, name="notificationtemplatetype"), nullable=False
    )
    locale: Mapped[str] = mapped_column(String(16), nullable=False, default="ru")
    subject_template: Mapped[str | None] = mapped_column(String(255), nullable=True)
    body_template: Mapped[str] = mapped_column(Text, nullable=False)
    title_template: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    variables_schema: Mapped[dict[str, object] | None] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=True
    )

    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "code", "channel", "locale", name="uq_notification_templates_scope"
        ),
        Index("ix_notification_templates_lookup", "tenant_id", "channel", "type", "is_active"),
    )


class NotificationChannelSettings(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "notification_channel_settings"

    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    email_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    telegram_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    inapp_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    email: Mapped[str | None] = mapped_column(String(255))
    telegram_chat_id: Mapped[str | None] = mapped_column(String(255))
    quiet_hours: Mapped[dict[str, str] | None] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=True
    )
    digest_mode: Mapped[str | None] = mapped_column(String(32), nullable=True)
    channel_preferences: Mapped[dict[str, object] | None] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=True
    )

    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "user_id", name="uq_notification_channel_settings_tenant_user"
        ),
    )


class Notification(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "notifications"

    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    channel: Mapped[NotificationChannel] = mapped_column(
        native_enum(NotificationChannel, name="notificationchannel"), nullable=False
    )
    type: Mapped[NotificationType] = mapped_column(
        native_enum(NotificationType, name="notificationtype"), nullable=False
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, object] | None] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=True
    )
    priority: Mapped[NotificationPriority] = mapped_column(
        native_enum(NotificationPriority, name="notificationpriority"),
        nullable=False,
        default=NotificationPriority.MEDIUM,
    )
    status: Mapped[NotificationStatus] = mapped_column(
        native_enum(NotificationStatus, name="notificationstatus"),
        nullable=False,
        default=NotificationStatus.QUEUED,
    )
    dedup_key: Mapped[str] = mapped_column(String(255), nullable=False)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempts: Mapped[int] = mapped_column(nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        Index("ix_notifications_queue", "tenant_id", "user_id", "status", "scheduled_at"),
        Index(
            "ix_notifications_dedup_active",
            "dedup_key",
            unique=True,
            sqlite_where=text("deleted_at IS NULL"),
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )


class ReminderEntityType(str, enum.Enum):
    TRAINING = "training"
    PPE = "ppe"
    MEDICAL = "medical"
    PERMIT = "permit"
    INSPECTION = "inspection"
    INCIDENT = "incident"
    DOCUMENT_JOB = "document_job"
    EDO = "edo"


class ReminderRule(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "reminder_rules"

    code: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    entity_type: Mapped[ReminderEntityType] = mapped_column(
        native_enum(ReminderEntityType, name="reminderentitytype"), nullable=False
    )
    date_field: Mapped[str] = mapped_column(String(64), nullable=False)
    schedule: Mapped[dict[str, object]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )
    recipients: Mapped[dict[str, object]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )
    action: Mapped[dict[str, object]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )

    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_reminder_rules_tenant_code"),)


class PlanTaskStatus(str, enum.Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    CANCELED = "canceled"
    OVERDUE = "overdue"


class PlanTask(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "plan_tasks"

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False)
    assignee_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[PlanTaskStatus] = mapped_column(
        native_enum(PlanTaskStatus, name="plantaskstatus_v2"),
        nullable=False,
        default=PlanTaskStatus.OPEN,
    )
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_plan_tasks_assignee_status_due", "tenant_id", "assignee_id", "status", "due_at"),
    )
