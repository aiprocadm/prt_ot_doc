"""Schemas for work permits (наряды-допуски)."""
from __future__ import annotations

from datetime import date, datetime

from pydantic import field_validator

from app.domains.work_permits import lifecycle as lc
from app.schemas.base import BaseSchema


class WorkPermitMemberCreate(BaseSchema):
    person_id: str
    role: str

    @field_validator("role")
    @classmethod
    def _role(cls, v: str) -> str:
        if not lc.is_member_role(v):
            raise ValueError(f"invalid role: {v!r}")
        return v


class WorkPermitMemberRead(BaseSchema):
    id: str
    person_id: str
    role: str
    created_at: datetime


class WorkPermitEventRead(BaseSchema):
    id: str
    event_type: str
    at: datetime
    actor_user_id: str | None
    photo_file_id: str | None
    note: str | None
    meta: dict | None = None


class WorkPermitCreate(BaseSchema):
    work_type: str
    zone_text: str
    number: str | None = None
    site_id: str | None = None
    equipment_text: str | None = None
    hazards_text: str | None = None
    measures_text: str | None = None
    planned_start: datetime | None = None
    planned_end: datetime | None = None
    subdivision_text: str | None = None
    content_text: str | None = None
    conditions_text: str | None = None
    safety_systems: list[str] | None = None
    measures_before_text: str | None = None
    measures_during_text: str | None = None
    special_conditions_text: str | None = None
    ppe_text: str | None = None

    @field_validator("work_type")
    @classmethod
    def _work_type(cls, v: str) -> str:
        if not lc.is_work_type(v):
            raise ValueError(f"invalid work_type: {v!r}")
        return v

    @field_validator("safety_systems")
    @classmethod
    def _safety_systems(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        for code in v:
            if not lc.is_safety_system(code):
                raise ValueError(f"invalid safety_system: {code!r}")
        return v


class WorkPermitUpdate(BaseSchema):
    work_type: str | None = None
    zone_text: str | None = None
    number: str | None = None
    site_id: str | None = None
    equipment_text: str | None = None
    hazards_text: str | None = None
    measures_text: str | None = None
    planned_start: datetime | None = None
    planned_end: datetime | None = None
    subdivision_text: str | None = None
    content_text: str | None = None
    conditions_text: str | None = None
    safety_systems: list[str] | None = None
    measures_before_text: str | None = None
    measures_during_text: str | None = None
    special_conditions_text: str | None = None
    ppe_text: str | None = None

    @field_validator("work_type")
    @classmethod
    def _work_type(cls, v: str | None) -> str | None:
        if v is not None and not lc.is_work_type(v):
            raise ValueError(f"invalid work_type: {v!r}")
        return v

    @field_validator("safety_systems")
    @classmethod
    def _safety_systems(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        for code in v:
            if not lc.is_safety_system(code):
                raise ValueError(f"invalid safety_system: {code!r}")
        return v


class WorkPermitRead(BaseSchema):
    id: str
    number: str | None
    work_type: str
    zone_text: str
    site_id: str | None
    equipment_text: str | None
    hazards_text: str | None
    measures_text: str | None
    planned_start: datetime | None
    planned_end: datetime | None
    status: str
    opened_at: datetime | None
    closed_at: datetime | None
    suspended_at: datetime | None
    members: list[WorkPermitMemberRead]
    subdivision_text: str | None
    content_text: str | None
    conditions_text: str | None
    safety_systems: list[str] | None
    measures_before_text: str | None
    measures_during_text: str | None
    special_conditions_text: str | None
    ppe_text: str | None
    created_at: datetime
    updated_at: datetime


class WorkPermitPage(BaseSchema):
    items: list[WorkPermitRead]
    total: int


class WorkPermitActionRequest(BaseSchema):
    photo_file_id: str | None = None
    note: str | None = None


class WorkPermitExtendRequest(BaseSchema):
    planned_end: datetime


class ViolationRead(BaseSchema):
    person_id: str
    role: str
    code: str
    severity: str


class ReadinessReportRead(BaseSchema):
    ok: bool
    violations: list[ViolationRead]


class WorkPermitBriefingCreate(BaseSchema):
    conducted_by_person_id: str | None = None
    conducted_at: datetime | None = None
    topics_text: str | None = None


class WorkPermitBriefingUpdate(BaseSchema):
    conducted_by_person_id: str | None = None
    conducted_at: datetime | None = None
    topics_text: str | None = None


class WorkPermitBriefingRead(BaseSchema):
    id: str
    work_permit_id: str
    conducted_by_person_id: str | None
    conducted_at: datetime | None
    topics_text: str | None
    created_at: datetime
    updated_at: datetime


class WorkPermitSignatureCreate(BaseSchema):
    person_id: str
    mode: str = "attested"

    @field_validator("mode")
    @classmethod
    def _mode(cls, v: str) -> str:
        if v not in ("attested", "code"):
            raise ValueError(f"invalid mode: {v!r}")
        return v


class WorkPermitSignatureRead(BaseSchema):
    id: str
    stream: str
    object_type: str
    object_id: str
    purpose: str
    status: str
    signer_person_id: str | None
    signer_name: str | None
    content_hash: str | None
    signed_at: datetime | None
    confirm_code: str | None = None


class WorkPermitDailyAdmissionCreate(BaseSchema):
    admission_date: date
    start_at: datetime | None = None
    end_at: datetime | None = None
    admitted_by_person_id: str | None = None
    note: str | None = None


class WorkPermitDailyAdmissionUpdate(BaseSchema):
    start_at: datetime | None = None
    end_at: datetime | None = None
    admitted_by_person_id: str | None = None
    note: str | None = None


class WorkPermitDailyAdmissionRead(BaseSchema):
    id: str
    work_permit_id: str
    admission_date: date
    start_at: datetime | None
    end_at: datetime | None
    admitted_by_person_id: str | None
    note: str | None
    created_at: datetime
    updated_at: datetime
