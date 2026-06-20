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
    evidence_file_ids: list[str] | None = Field(default=None)
    note: str | None = Field(default=None, min_length=1)


class EvidenceFileRef(BaseSchema):
    """A file attached to a prescription as evidence (FileLink role="evidence")."""

    file_id: str
    role: str
    status: str
    display_name: str | None = None
    size: int | None = None


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
    evidence_files: list[EvidenceFileRef] = Field(default_factory=list)


class PrescriptionPage(BaseSchema):
    items: list[PrescriptionRead]
    total: int


class PrescriptionSummary(BaseSchema):
    by_status: dict[str, int]
    total: int
    overdue_count: int
    closure_rate: float
