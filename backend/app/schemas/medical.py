"""Medical requirement and registry schemas."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class MedicalRequirementCreate(BaseModel):
    person_id: str = Field(..., min_length=1, max_length=36)
    due_date: date | None = None
    notes: str | None = None

    model_config = ConfigDict(extra="forbid")


class MedicalExamRead(BaseModel):
    id: str
    person_id: str
    exam_type: str
    exam_date: date
    conclusion: str | None = None
    valid_until: date
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MedicalExamPage(BaseModel):
    items: list[MedicalExamRead]
    total: int
