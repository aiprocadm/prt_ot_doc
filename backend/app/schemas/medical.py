"""Medical requirement and registry schemas."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.models import (
    MedicalExamKind,
    MedicalFitness,
    MedicalReferralStatus,
    MedicalSuspensionReason,
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
    psychiatric_protocol_no: str | None = None
    psychiatric_activity_codes: list[str] = Field(default_factory=list)

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
    psychiatric_protocol_no: str | None = None
    psychiatric_activity_codes: list[str] = Field(default_factory=list)
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


class MedicalNormUpdate(BaseModel):
    """Partial update body for PATCH /medical/norms/{norm_id}. position_id is intentionally excluded — changing it would re-key the norm; delete + recreate instead."""

    exam_kind: MedicalExamKind | None = None
    hazard_id: str | None = None
    interval_days: int | None = Field(default=None, ge=0, le=3650)
    working_conditions_class: str | None = None
    model_config = ConfigDict(extra="forbid")


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


class MedicalFactorCreate(BaseModel):
    code: str = Field(..., min_length=1, max_length=32)
    name: str = Field(..., min_length=1, max_length=255)
    category: Literal["factor", "work"] = "factor"
    exam_kinds: list[MedicalExamKind] = Field(..., min_length=1)
    periodicity_months: int = Field(default=12, ge=1, le=120)
    participants: list[str] | None = None
    lab_tests: list[str] | None = None
    model_config = ConfigDict(extra="forbid")


class MedicalFactorRead(BaseModel):
    id: str
    code: str
    name: str
    category: str
    exam_kinds: list[str]
    periodicity_months: int
    participants: list[str] | None = None
    lab_tests: list[str] | None = None
    model_config = ConfigDict(from_attributes=True)


class MedicalFactorUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    category: Literal["factor", "work"] | None = None
    exam_kinds: list[MedicalExamKind] | None = None
    periodicity_months: int | None = Field(default=None, ge=1, le=120)
    participants: list[str] | None = None
    lab_tests: list[str] | None = None
    model_config = ConfigDict(extra="forbid")


class MedicalFactorPage(BaseModel):
    items: list[MedicalFactorRead]
    total: int


class FactorRef(BaseModel):
    code: str
    name: str


class ContingentRegisterRow(BaseModel):
    position_id: str
    position_name: str
    factors: list[FactorRef]
    headcount: int
    exam_kinds: list[str]
    periodicity_months: int | None = None


class ContingentRegisterPage(BaseModel):
    items: list[ContingentRegisterRow]
    total: int


class NamedListRow(BaseModel):
    person_id: str
    full_name: str
    position_name: str | None = None
    department: str | None = None
    factors: list[FactorRef]
    required_kinds: list[str]
    last_exam_date: date | None = None
    next_due_date: date | None = None
    status: str


class NamedListPage(BaseModel):
    items: list[NamedListRow]
    total: int


class HazardFactorMappingIn(BaseModel):
    """Runtime-привязка вредного фактора 29н к карте опасности.

    `factor_code=None` снимает привязку.
    """

    factor_code: str | None = Field(default=None, max_length=32)
    model_config = ConfigDict(extra="forbid")


class HazardFactorMappingRead(BaseModel):
    hazard_id: str
    hazard_code: str
    hazard_title: str
    factor_code: str | None = None
    factor_name: str | None = None


class HazardFactorMappingPage(BaseModel):
    items: list[HazardFactorMappingRead]
    total: int


class PsychiatricActivityTypeCreate(BaseModel):
    code: str = Field(..., min_length=1, max_length=32)
    name: str = Field(..., min_length=1, max_length=255)
    interval_days: int = Field(default=1825, ge=1, le=3650)
    model_config = ConfigDict(extra="forbid")


class PsychiatricActivityTypeRead(BaseModel):
    id: str
    code: str
    name: str
    interval_days: int
    model_config = ConfigDict(from_attributes=True)


class PsychiatricActivityTypeUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    interval_days: int | None = Field(default=None, ge=1, le=3650)
    model_config = ConfigDict(extra="forbid")


class PsychiatricActivityTypePage(BaseModel):
    items: list[PsychiatricActivityTypeRead]
    total: int


class PositionActivitiesIn(BaseModel):
    """Full replacement of a position's mapped 695 activity codes."""

    activity_codes: list[str] = Field(default_factory=list)
    model_config = ConfigDict(extra="forbid")


class PositionActivitiesRead(BaseModel):
    position_id: str
    activity_codes: list[str]


class PositionActivitiesPage(BaseModel):
    items: list[PositionActivitiesRead]
    total: int
