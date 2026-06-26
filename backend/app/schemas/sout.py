"""Pydantic schemas for СОУТ срез-1 (P10-04)."""
from __future__ import annotations

from datetime import date, datetime

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
    assessed_class: SoutClass | None = None
    assessment_date: date | None = None
    next_assessment_date: date | None = None


class WorkplaceUpdate(BaseSchema):
    workplace_code: str | None = None
    position_name: str | None = None
    person_id: str | None = None
    assessed_class: SoutClass | None = None
    assessment_date: date | None = None
    next_assessment_date: date | None = None


class WorkplaceRead(BaseSchema):
    id: str
    campaign_id: str
    workplace_code: str
    position_name: str
    person_id: str | None
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


class FactorRead(BaseSchema):
    id: str
    workplace_id: str
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
