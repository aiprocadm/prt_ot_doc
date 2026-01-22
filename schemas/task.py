"""Pydantic schemas describing asynchronous task state."""
from __future__ import annotations

from typing import Any

from pydantic import Field

from app.schemas.base import BaseSchema


class TaskAcceptedResponse(BaseSchema):
    """Response payload returned when background work is enqueued."""

    task_id: str = Field(..., description="Identifier of the scheduled task")
    status_url: str = Field(..., description="URL to poll task status")


class TaskStatusResponse(BaseSchema):
    """Describe the observed status of a background task."""

    task_id: str = Field(..., description="Identifier of the tracked task")
    status: str = Field(
        ..., description="Current pipeline status; Celery state is reported in metadata"
    )
    document_id: str | None = Field(
        default=None, description="Rendered document identifier when available"
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
