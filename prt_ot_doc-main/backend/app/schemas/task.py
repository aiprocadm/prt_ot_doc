"""Pydantic schemas describing asynchronous task state."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from app.schemas.base import BaseSchema


class TaskAcceptedResponse(BaseSchema):
    """Response payload returned when background work is enqueued."""

    task_id: str = Field(..., description="Identifier of the scheduled task")
    job_id: str | None = Field(default=None, description="Document job identifier")
    correlation_id: str | None = Field(default=None, description="Correlation identifier")
    status_url: str = Field(..., description="URL to poll task status")
    document_version_id: str | None = Field(
        default=None,
        description="Document version identifier when already available",
    )


class TaskStatusResponse(BaseSchema):
    """Describe the observed status of a background task."""

    task_id: str = Field(..., description="Identifier of the tracked task")
    status: str = Field(
        ..., description="Current pipeline status; Celery state is reported in metadata"
    )
    document_id: str | None = Field(
        default=None, description="Rendered document identifier when available"
    )
    document_version_id: str | None = Field(
        default=None, description="Document version identifier when available"
    )
    error: str | None = Field(
        default=None, description="Short error code if the task failed"
    )
    metadata: dict[str, Any] | None = Field(
        default=None, description="Additional metadata about the task execution"
    )
    result: dict[str, Any] | None = Field(
        default=None, description="Structured payload returned by the task on success"
    )


class TaskRead(BaseSchema):
    id: str
    title: str
    description: str | None = None
    entity_type: str | None = None
    entity_id: str | None = None
    due_at: datetime | None = None
    status: str
    assignee_id: str | None = None
    created_by: str | None = None
    priority: str
    next_remind_at: datetime | None = None
    reminder_channel: str | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    overdue: bool = False


class TaskCreate(BaseSchema):
    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    entity_type: str | None = Field(default=None, max_length=64)
    entity_id: str | None = Field(default=None, max_length=36)
    due_at: datetime | None = None
    assignee_id: str | None = Field(default=None, max_length=36)
    priority: str | None = Field(default=None)


class TaskUpdate(BaseSchema):
    title: str | None = Field(default=None, max_length=255)
    description: str | None = None
    due_at: datetime | None = None
    status: str | None = None
    assignee_id: str | None = Field(default=None, max_length=36)
    priority: str | None = None


class TaskPagination(BaseSchema):
    page: int
    page_size: int
    total: int


class TaskListResponse(BaseSchema):
    items: list[TaskRead]
    pagination: TaskPagination
