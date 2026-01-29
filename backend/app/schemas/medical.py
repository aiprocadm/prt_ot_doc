"""Medical requirement schemas."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class MedicalRequirementCreate(BaseModel):
    person_id: str = Field(..., min_length=1, max_length=36)
    due_date: date | None = None
    notes: str | None = None

    model_config = ConfigDict(extra="forbid")
