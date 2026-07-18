"""Pydantic schemas for СОУТ срез-1 (P10-04)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from app.models.sout import SoutCampaignStatus, SoutClass, SoutGuaranteeKind
from app.schemas.base import BaseSchema


# --- Campaign ---
class CampaignCreate(BaseSchema):
    name: str
    expert_org_name: str | None = None
    report_number: str | None = None
    report_date: date | None = None
    planned_date: date | None = None


class CampaignUpdate(BaseSchema):
    name: str | None = None
    expert_org_name: str | None = None
    report_number: str | None = None
    report_date: date | None = None
    planned_date: date | None = None
    completed_date: date | None = None


class CampaignStatusUpdate(BaseSchema):
    status: SoutCampaignStatus


class CampaignRead(BaseSchema):
    id: str
    name: str
    expert_org_name: str | None
    report_number: str | None
    report_date: date | None
    status: SoutCampaignStatus
    planned_date: date | None
    completed_date: date | None
    created_at: datetime
    updated_at: datetime


class CampaignPage(BaseSchema):
    items: list[CampaignRead]
    total: int
    limit: int
    offset: int


# --- Workplace ---
class WorkplaceCreate(BaseSchema):
    workplace_code: str
    position_name: str
    person_id: str | None = None
    position_id: str | None = None
    assessed_class: SoutClass | None = None
    assessment_date: date | None = None
    next_assessment_date: date | None = None


class WorkplaceUpdate(BaseSchema):
    workplace_code: str | None = None
    position_name: str | None = None
    person_id: str | None = None
    position_id: str | None = None
    assessed_class: SoutClass | None = None
    assessment_date: date | None = None
    next_assessment_date: date | None = None


class WorkplaceRead(BaseSchema):
    id: str
    campaign_id: str
    workplace_code: str
    position_name: str
    person_id: str | None
    position_id: str | None = None
    assessed_class: SoutClass | None
    assessment_date: date | None
    next_assessment_date: date | None
    is_reassessment_due: bool
    created_at: datetime
    updated_at: datetime


class WorkplacePage(BaseSchema):
    items: list[WorkplaceRead]
    total: int
    limit: int
    offset: int


# --- Factor ---
class FactorCreate(BaseSchema):
    name: str
    code: str | None = None
    measured_class: SoutClass | None = None
    note: str | None = None
    hazard_id: str | None = None


class FactorUpdate(BaseSchema):
    name: str | None = None
    code: str | None = None
    measured_class: SoutClass | None = None
    note: str | None = None
    hazard_id: str | None = None


class FactorRead(BaseSchema):
    id: str
    workplace_id: str
    hazard_id: str | None = None
    code: str | None
    name: str
    measured_class: SoutClass | None
    note: str | None


# --- Guarantee ---
class GuaranteeCreate(BaseSchema):
    kind: SoutGuaranteeKind
    detail: str | None = None


class GuaranteeRead(BaseSchema):
    id: str
    workplace_id: str
    kind: SoutGuaranteeKind
    detail: str | None


# --- Class history (срез-2) ---
class ClassHistoryRead(BaseSchema):
    id: str
    workplace_id: str
    old_class: SoutClass | None
    new_class: SoutClass | None
    changed_at: datetime
    note: str | None
    is_worsening: bool


# --- Report projection ---
class WorkplaceReport(BaseSchema):
    workplace: WorkplaceRead
    factors: list[FactorRead]
    guarantees: list[GuaranteeRead]


class CampaignReport(BaseSchema):
    campaign: CampaignRead
    workplaces: list[WorkplaceReport]


# --- Norm suggestions (срез-3) ---
class PpeNormSuggestion(BaseSchema):
    position_id: str
    hazard_id: str
    hazard_title: str
    factor_name: str
    factor_code: str | None
    measured_class: SoutClass | None
    reason: str


class MedicalExamSuggestion(BaseSchema):
    position_id: str
    exam_kind: str
    periodicity_months: int
    factor_codes: list[str]
    reason: str


class NormSuggestions(BaseSchema):
    ppe: list[PpeNormSuggestion]
    medical: list[MedicalExamSuggestion]


# --- Class cascade (срез-6) ---
class CascadeMedicalAction(BaseSchema):
    exam_kind: str
    op: Literal["create", "reclass", "conflict"]
    periodicity_months: int
    interval_days: int
    target_class: str
    current_class: str | None = None
    factor_codes: list[str] = []
    reason: str


class CascadePreview(BaseSchema):
    assessed_class: str | None
    can_apply: bool
    medical: list[CascadeMedicalAction] = []
    ppe_advisory: list[PpeNormSuggestion] = []


class CascadeResult(BaseSchema):
    created: int
    reclassified: int
    conflicts: int
    ppe_advisory_count: int


# --- Declaration of conformity (срез-4) ---
class DeclarationRowRead(BaseSchema):
    workplace_code: str
    position_name: str
    assessed_class: str | None
    headcount: str
    report_ref: str | None
    eligible: bool
    ineligible_reason: str | None


class DeclarationPreview(BaseSchema):
    campaign_id: str
    campaign_name: str
    eligible: list[DeclarationRowRead]
    ineligible: list[DeclarationRowRead]
    eligible_count: int
    ineligible_count: int


# --- Import of СОУТ report (срез-5) ---
class ImportFactorRow(BaseSchema):
    code: str | None
    name: str
    parsed_class: str | None
    class_unparsed: str | None


class ImportWorkplaceRow(BaseSchema):
    row_index: int
    workplace_code: str
    position_name: str
    parsed_class: str | None
    current_class: str | None
    change: Literal["new", "changed", "unchanged", "removed"]
    factors: list[ImportFactorRow]
    errors: list[str]
    warnings: list[str]


class ImportPreview(BaseSchema):
    campaign_id: str
    rows: list[ImportWorkplaceRow]
    new_count: int
    changed_count: int
    unchanged_count: int
    removed_count: int
    error_count: int
    can_apply: bool


class ImportResult(BaseSchema):
    campaign_id: str
    created: int
    updated: int
    skipped: int
    removed_detected: int
    errors: list[str]
