"""Pydantic schemas for incidents and inspections."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import Field, computed_field

from app.models.models import (
    IncidentSeverity,
    IncidentStage,
    IncidentStatus,
    IncidentType,
    InspectionStatus,
)
from app.schemas.base import BaseSchema


class IncidentCreate(BaseSchema):
    title: str = Field(min_length=1, max_length=255)
    incident_type: IncidentType
    occurred_at: datetime
    company_id: str = Field(min_length=1, max_length=36)
    site_id: str = Field(min_length=1, max_length=36)
    severity: IncidentSeverity = IncidentSeverity.MEDIUM
    description: str | None = None
    location_description: str | None = Field(default=None, max_length=255)
    pack_id: str | None = Field(default=None, min_length=1, max_length=36)
    victim_ids: list[str] = Field(default_factory=list)


class IncidentUpdate(BaseSchema):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    incident_type: IncidentType | None = None
    occurred_at: datetime | None = None
    company_id: str | None = Field(default=None, min_length=1, max_length=36)
    site_id: str | None = Field(default=None, min_length=1, max_length=36)
    severity: IncidentSeverity | None = None
    status: IncidentStatus | None = None
    investigation_stage: IncidentStage | None = None
    description: str | None = None
    location_description: str | None = Field(default=None, max_length=255)
    pack_id: str | None = Field(default=None, min_length=1, max_length=36)
    victim_ids: list[str] | None = None


class IncidentRead(BaseSchema):
    id: str
    title: str
    description: str | None
    incident_type: IncidentType
    occurred_at: datetime
    company_id: str
    site_id: str
    severity: IncidentSeverity
    status: IncidentStatus
    investigation_stage: IncidentStage
    location_description: str | None
    pack_id: str | None
    victim_ids: list[str] = Field(default_factory=list)


class IncidentPage(BaseSchema):
    items: list[IncidentRead]
    total: int


class IncidentLogCreate(BaseSchema):
    stage: IncidentStage
    status: IncidentStatus
    message: str = Field(min_length=1, max_length=5000)
    metadata_json: dict = Field(default_factory=dict)


class IncidentLogRead(BaseSchema):
    id: str
    incident_id: str
    author_id: str | None
    stage: IncidentStage
    status: IncidentStatus
    message: str
    metadata_json: dict
    created_at: datetime


class InspectionCreate(BaseSchema):
    company_id: str = Field(min_length=1, max_length=36)
    site_id: str | None = Field(default=None, min_length=1, max_length=36)
    authority: str = Field(min_length=1, max_length=255)
    purpose: str | None = Field(default=None, max_length=255)
    scheduled_at: date | None = None
    status: InspectionStatus = InspectionStatus.PLANNED
    started_at: datetime | None = None


class InspectionUpdate(BaseSchema):
    company_id: str | None = Field(default=None, min_length=1, max_length=36)
    site_id: str | None = Field(default=None, min_length=1, max_length=36)
    authority: str | None = Field(default=None, max_length=255)
    purpose: str | None = Field(default=None, max_length=255)
    scheduled_at: date | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    status: InspectionStatus | None = None
    result_summary: str | None = None


class InspectionResultCreate(BaseSchema):
    title: str = Field(min_length=1, max_length=255)
    outcome: str | None = Field(default=None, max_length=128)
    notes: str | None = None
    issued_at: date | None = None
    file_id: str | None = Field(default=None, min_length=1, max_length=36)


class InspectionResultRead(BaseSchema):
    id: str
    inspection_id: str
    title: str
    outcome: str | None
    notes: str | None
    issued_at: date | None
    file_id: str | None
    created_at: datetime


class InspectionRead(BaseSchema):
    id: str
    company_id: str
    site_id: str | None
    authority: str
    purpose: str | None
    scheduled_at: date | None
    started_at: datetime | None
    finished_at: datetime | None
    status: InspectionStatus
    result_summary: str | None
    results: list[InspectionResultRead] = Field(default_factory=list)


class InspectionPage(BaseSchema):
    items: list[InspectionRead]
    total: int
