"""Models for deadlines, obligations, and task reminders."""

from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import TenantBaseModel, native_enum

if TYPE_CHECKING:  # pragma: no cover
    from app.models.models import User

__all__ = ["Task", "TaskPriority", "TaskReminderChannel", "TaskStatus"]


class TaskStatus(str, enum.Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    CANCELLED = "cancelled"


class TaskPriority(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TaskReminderChannel(str, enum.Enum):
    IN_APP = "in_app"
    EMAIL = "email"


class Task(TenantBaseModel):
    """Tenant-scoped obligation or reminder task."""

    __tablename__ = "task"

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    entity_type: Mapped[str | None] = mapped_column(String(64))
    entity_id: Mapped[str | None] = mapped_column(String(36))
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[TaskStatus] = mapped_column(
        native_enum(TaskStatus, name="taskstatus"), nullable=False, default=TaskStatus.OPEN
    )
    assignee_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("user.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("user.id", ondelete="SET NULL"), nullable=True, index=True
    )
    priority: Mapped[TaskPriority] = mapped_column(
        native_enum(TaskPriority, name="taskpriority"),
        nullable=False,
        default=TaskPriority.MEDIUM,
    )
    next_remind_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reminder_channel: Mapped[TaskReminderChannel | None] = mapped_column(
        native_enum(TaskReminderChannel, name="taskreminderchannel"), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    assignee: Mapped["User | None"] = relationship(
        "User",
        foreign_keys=[assignee_id],
        lazy="joined",
    )
    creator: Mapped["User | None"] = relationship(
        "User",
        foreign_keys=[created_by],
        lazy="joined",
    )

    __table_args__ = (
        Index("ix_task_status", "tenant_id", "status"),
        Index("ix_task_due", "tenant_id", "due_at"),
    )
