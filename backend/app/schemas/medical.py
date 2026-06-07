"""Medical requirement and registry schemas."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.models import (
    MedicalExamKind, MedicalFitness, MedicalReferralStatus, MedicalSuspensionReason,
    MedicalSuspensionStatus,
)


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
    exam_kind: MedicalExamKind | None = None
    fitness: MedicalFitness | None = None
    restrictions: str | None = None
    contraindications: list[str] = Field(default_factory=list)
    referral_id: str | None = None
    medical_org_name: str | None = None

    model_config = ConfigDict(from_attributes=True)


class MedicalExamPage(BaseModel):
    items: list[MedicalExamRead]
    total: int


class MedicalExamCreate(BaseModel):
    person_id: str = Field(..., min_length=1, max_length=36)
    exam_kind: MedicalExamKind
    exam_date: date
    fitness: MedicalFitness | None = None
    conclusion: str | None = None
    restrictions: str | None = None
    contraindications: list[str] = Field(default_factory=list)
    valid_until: date | None = None
    medical_org_name: str | None = None
    referral_id: str | None = None
    exam_type: str | None = None  # legacy free label; defaults from exam_kind
    model_config = ConfigDict(extra="forbid")


class MedicalExamUpdate(BaseModel):
    fitness: MedicalFitness | None = None
    conclusion: str | None = None
    restrictions: str | None = None
    contraindications: list[str] | None = None
    valid_until: date | None = None
    model_config = ConfigDict(extra="forbid")


class MedicalNormCreate(BaseModel):
    position_id: str = Field(..., min_length=1, max_length=36)
    exam_kind: MedicalExamKind
    hazard_id: str | None = None
    interval_days: int = Field(default=365, ge=0, le=3650)
    working_conditions_class: str | None = None
    model_config = ConfigDict(extra="forbid")


class MedicalNormRead(BaseModel):
    id: str
    position_id: str
    hazard_id: str | None = None
    exam_kind: MedicalExamKind
    interval_days: int
    working_conditions_class: str | None = None
    model_config = ConfigDict(from_attributes=True)


class MedicalNormPage(BaseModel):
    items: list[MedicalNormRead]
    total: int


class MedicalReferralCreate(BaseModel):
    person_id: str = Field(..., min_length=1, max_length=36)
    exam_kind: MedicalExamKind
    due_at: date | None = None
    medical_org_name: str | None = None
    model_config = ConfigDict(extra="forbid")


class MedicalReferralTransition(BaseModel):
    to: MedicalReferralStatus
    result_exam_id: str | None = None
    note: str | None = None
    model_config = ConfigDict(extra="forbid")


class MedicalReferralRead(BaseModel):
    id: str
    person_id: str
    exam_kind: MedicalExamKind
    due_at: date | None = None
    status: MedicalReferralStatus
    medical_org_name: str | None = None
    result_exam_id: str | None = None
    is_overdue: bool = False
    model_config = ConfigDict(from_attributes=True)


class MedicalReferralPage(BaseModel):
    items: list[MedicalReferralRead]
    total: int


class ContingentItem(BaseModel):
    person_id: str
    exam_kind: MedicalExamKind
    status: str  # ContingentItemStatus value
    valid_until: date | None = None
    due_at: date | None = None
    model_config = ConfigDict(from_attributes=True)


class ContingentPage(BaseModel):
    items: list[ContingentItem]
    total: int


class MedicalSummary(BaseModel):
    by_status: dict[str, int]
    total: int
    overdue_count: int
    suspended_count: int


class MedicalSuspensionRead(BaseModel):
    id: str
    person_id: str
    reason: MedicalSuspensionReason
    status: MedicalSuspensionStatus
    source_exam_id: str | None = None
    model_config = ConfigDict(from_attributes=True)


class MedicalSuspensionPage(BaseModel):
    items: list[MedicalSuspensionRead]
    total: int
