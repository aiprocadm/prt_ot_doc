"""Schemas for inspection prescriptions."""
from __future__ import annotations

from datetime import date, datetime

from pydantic import Field

from app.models.models import PrescriptionStatus
from app.schemas.base import BaseSchema


class PrescriptionCreate(BaseSchema):
    inspection_id: str = Field(min_length=1, max_length=36)
    incident_id: str | None = Field(default=None, min_length=1, max_length=36)
    description: str = Field(min_length=1)
    due_at: date | None = None
    assignee_id: str | None = Field(default=None, min_length=1, max_length=36)


class PrescriptionUpdate(BaseSchema):
    inspection_id: str | None = Field(default=None, min_length=1, max_length=36)
    incident_id: str | None = Field(default=None, min_length=1, max_length=36)
    description: str | None = Field(default=None, min_length=1)
    due_at: date | None = None
    assignee_id: str | None = Field(default=None, min_length=1, max_length=36)


class PrescriptionTransition(BaseSchema):
    """Body for POST /prescriptions/{id}/transition."""

    to: PrescriptionStatus
    evidence: str | None = Field(default=None, min_length=1)
    note: str | None = Field(default=None, min_length=1)


class PrescriptionRead(BaseSchema):
    id: str
    inspection_id: str
    incident_id: str | None
    description: str
    due_at: date | None
    status: PrescriptionStatus
    assignee_id: str | None
    evidence: str | None
    closed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    is_overdue: bool = False


class PrescriptionPage(BaseSchema):
    items: list[PrescriptionRead]
    total: int
