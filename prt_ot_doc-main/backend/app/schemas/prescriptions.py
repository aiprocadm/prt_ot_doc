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
    status: PrescriptionStatus = PrescriptionStatus.OPEN
    assignee_id: str | None = Field(default=None, min_length=1, max_length=36)


class PrescriptionUpdate(BaseSchema):
    inspection_id: str | None = Field(default=None, min_length=1, max_length=36)
    incident_id: str | None = Field(default=None, min_length=1, max_length=36)
    description: str | None = Field(default=None, min_length=1)
    due_at: date | None = None
    status: PrescriptionStatus | None = None
    assignee_id: str | None = Field(default=None, min_length=1, max_length=36)


class PrescriptionRead(BaseSchema):
    id: str
    inspection_id: str
    incident_id: str | None
    description: str
    due_at: date | None
    status: PrescriptionStatus
    assignee_id: str | None
    created_at: datetime
    updated_at: datetime


class PrescriptionPage(BaseSchema):
    items: list[PrescriptionRead]
    total: int
