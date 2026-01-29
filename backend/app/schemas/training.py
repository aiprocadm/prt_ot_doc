"""Schemas for training module."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import AliasChoices, Field

from app.models.models import TrainingSessionStatus
from app.schemas.base import BaseSchema


class TrainingCourseBase(BaseSchema):
    title: str
    code: str | None = None
    description: str | None = None
    duration_hours: int | None = Field(default=None, ge=0)
    valid_period_days: int | None = Field(default=None, ge=1)
    metadata_json: dict = Field(
        default_factory=dict,
        serialization_alias="metadata",
        validation_alias=AliasChoices("metadata", "metadata_json"),
    )


class TrainingCourseCreate(TrainingCourseBase):
    pass


class TrainingCourseUpdate(BaseSchema):
    title: str | None = None
    code: str | None = None
    description: str | None = None
    duration_hours: int | None = Field(default=None, ge=0)
    valid_period_days: int | None = Field(default=None, ge=1)
    metadata_json: dict | None = Field(
        default=None,
        serialization_alias="metadata",
        validation_alias=AliasChoices("metadata", "metadata_json"),
    )


class TrainingCourseRead(TrainingCourseBase):
    id: str
    created_at: datetime
    updated_at: datetime


class TrainingCoursePage(BaseSchema):
    items: list[TrainingCourseRead]
    total: int


class TrainingPlanCreate(BaseSchema):
    company_id: str
    course_id: str
    position_id: str | None = None
    person_id: str | None = None
    due_date: date | None = None
    is_mandatory: bool = True


class TrainingPlanRead(BaseSchema):
    id: str
    company_id: str
    course_id: str
    position_id: str | None = None
    person_id: str | None = None
    due_date: date | None = None
    is_mandatory: bool
    assigned_at: datetime
    created_at: datetime
    updated_at: datetime


class TrainingSessionCreate(BaseSchema):
    person_id: str
    course_id: str
    plan_id: str | None = None
    status: TrainingSessionStatus = TrainingSessionStatus.COMPLETED
    started_at: datetime | None = None
    completed_at: datetime | None = None
    score: int | None = Field(default=None, ge=0)
    notes: str | None = None


class TrainingSessionRead(BaseSchema):
    id: str
    person_id: str
    course_id: str
    plan_id: str | None = None
    status: TrainingSessionStatus
    started_at: datetime | None = None
    completed_at: datetime | None = None
    score: int | None = None
    notes: str | None = None
    created_at: datetime
    updated_at: datetime


class TrainingCertificateCreate(BaseSchema):
    person_id: str
    course_id: str
    plan_id: str | None = None
    session_id: str | None = None
    file_id: str | None = None
    number: str | None = None
    issued_at: date | None = None
    valid_until: date | None = None
    permit_type: str | None = None
    position_id: str | None = None


class TrainingCertificateRead(BaseSchema):
    id: str
    person_id: str
    course_id: str
    plan_id: str | None = None
    session_id: str | None = None
    file_id: str | None = None
    number: str | None = None
    issued_at: date
    valid_until: date | None = None
    created_at: datetime
    updated_at: datetime


class TrainingCertificatePage(BaseSchema):
    items: list[TrainingCertificateRead]
    total: int
