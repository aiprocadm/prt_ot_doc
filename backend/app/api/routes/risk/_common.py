"""Risk endpoints — shared foundation (ARCH-4 slice 6 split).

Both routers (``router`` for /risks, ``engine_router`` mounted at /risk), the logger,
access dependencies, constants, helper functions and all request/response models
shared by the methodologies, assessments and reports endpoint modules.
"""

from __future__ import annotations

import logging
import re
from datetime import date
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.core.errors import api_problem_detail
from app.core.screen_access import screen_roles
from app.core.security import AccessContext, abac, rbac
from app.models.models import (
    RiskMethodology,
    Tenant,
)
from app.models.risk import (
    RiskControl,
)

router = APIRouter(tags=["risks"])
engine_router = APIRouter(prefix="/risk", tags=["risk"])

logger = logging.getLogger("app.risk")

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[Tenant, Depends(get_tenant_record)]
EditorAccess = Annotated[AccessContext, Depends(rbac(["admin"]))]
AdminAccess = Annotated[AccessContext, Depends(rbac(["admin"]))]

# Роли берутся из единой карты прав экрана (core/screen_access): пункт меню
# виден ровно тем, кого пускает ручка — иначе человек видит раздел и получает
# 403 (docs/audit/ACCESS_MENU_VS_API.md, сторож tests/test_menu_matches_api.py).
_RISK_READ_ROLES = list(screen_roles("risk.view"))


def _tenant_resource_id(tenant: Tenant = Depends(get_tenant_record)) -> str | None:
    return getattr(tenant, "id", None)


RiskReadAccess = Annotated[
    AccessContext,
    Depends(abac(_tenant_resource_id, required_roles=_RISK_READ_ROLES, action="read risks")),
]


def _risk_unprocessable(message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=api_problem_detail(code="RISK_VALIDATION_ERROR", message=message, error_type="risk"),
    )


def _risk_bad_request(message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=api_problem_detail(code="RISK_BAD_REQUEST", message=message, error_type="risk"),
    )


async def _get_tenant_entity(session: AsyncSession, model: type, tenant_id: str, entity_id: str):
    record = await session.get(model, entity_id)
    if record is None or getattr(record, "tenant_id", None) != tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Entity not found")
    return record


async def _resolve_controls(
    session: AsyncSession,
    *,
    tenant_id: str,
    control_codes: list[str],
) -> dict[str, RiskControl]:
    if not control_codes:
        return {}
    stmt = select(RiskControl).where(
        RiskControl.tenant_id == tenant_id,
        RiskControl.code.in_(control_codes),
    )
    controls = (await session.execute(stmt)).scalars().all()
    return {control.code: control for control in controls}


def _slugify_code(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower()).strip("_")
    return normalized[:64] or "default_matrix"


def _default_methodology_definition() -> dict[str, object]:
    return {
        "severity_scale": [{"value": idx, "label": str(idx)} for idx in range(1, 6)],
        "likelihood_scale": [{"value": idx, "label": str(idx)} for idx in range(1, 6)],
        "bands": [
            {"name": "low", "max": 4},
            {"name": "med", "max": 9},
            {"name": "high", "max": 16},
            {"name": "crit", "max": 25},
        ],
    }


def _band_from_definition(definition: dict[str, object], score: int) -> str:
    raw_bands = definition.get("bands", []) if isinstance(definition, dict) else []
    if isinstance(raw_bands, list):
        candidates: list[tuple[int, str]] = []
        for candidate in raw_bands:
            if not isinstance(candidate, dict):
                continue
            name = candidate.get("name")
            limit = candidate.get("max")
            if isinstance(name, str) and isinstance(limit, int):
                candidates.append((limit, name))
        for limit, band in sorted(candidates, key=lambda pair: pair[0]):
            if score <= limit:
                return band
    if score <= 4:
        return "low"
    if score <= 9:
        return "med"
    if score <= 16:
        return "high"
    return "crit"


def _risk_level_filter(level: str) -> tuple[int | None, int | None]:
    normalized = level.lower()
    if normalized == "low":
        return (None, 4)
    if normalized in {"med", "medium"}:
        return (5, 9)
    if normalized == "high":
        return (10, 16)
    if normalized in {"crit", "critical"}:
        return (17, None)
    raise ValueError("Unsupported risk level")


async def _get_or_create_default_methodology(
    session: AsyncSession, tenant_id: str
) -> RiskMethodology:
    stmt = select(RiskMethodology).where(
        RiskMethodology.tenant_id == tenant_id,
        RiskMethodology.code == "default_matrix",
    )
    existing = (await session.execute(stmt)).scalar_one_or_none()
    if existing is not None:
        return existing
    methodology = RiskMethodology(
        tenant_id=tenant_id,
        code="default_matrix",
        name="Default Matrix",
        definition=_default_methodology_definition(),
    )
    session.add(methodology)
    await session.flush()
    return methodology


class HazardMeasureIn(BaseModel):
    text: str = Field(..., min_length=2, max_length=512)
    owner_role: str | None = Field(default=None, max_length=64)
    owner_id: str | None = Field(default=None, max_length=64)
    due_in_days: int | None = Field(default=None, ge=0, le=3650)

    model_config = ConfigDict(extra="forbid")


class HazardIn(BaseModel):
    code: str = Field(..., min_length=2, max_length=64)
    title: str = Field(..., min_length=2, max_length=256)
    module: str = Field(default="ot", pattern=r"^(ot|pb|prom|eco|siz|common)$")
    description: str | None = None
    recommended_measures: list[HazardMeasureIn] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class ControlIn(BaseModel):
    code: str = Field(..., min_length=1, max_length=64)
    title: str = Field(..., min_length=2, max_length=256)
    type: str = Field(default="org", pattern=r"^(org|tech|ppe|train)$")
    description: str | None = None

    model_config = ConfigDict(extra="forbid")


class MatrixRow(BaseModel):
    severity: int = Field(..., ge=1, le=5)
    likelihood: int = Field(..., ge=1, le=5)
    score: int = Field(..., ge=1)
    band: str = Field(..., pattern=r"^(low|med|high|crit)$")

    model_config = ConfigDict(extra="forbid")


class MatrixUp(BaseModel):
    methodology_id: str | None = None
    rows: list[MatrixRow] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class BandDef(BaseModel):
    name: str = Field(..., pattern=r"^(low|med|high|crit)$")
    max: int = Field(..., ge=1)

    model_config = ConfigDict(extra="forbid")


class ScaleItem(BaseModel):
    value: int = Field(..., ge=1)
    label: str = Field(..., min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=512)

    model_config = ConfigDict(extra="forbid")


class MethodologyIn(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    code: str | None = Field(default=None, min_length=2, max_length=64)
    severity_scale: list[ScaleItem] = Field(default_factory=list)
    likelihood_scale: list[ScaleItem] = Field(default_factory=list)
    bands: list[BandDef] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class MethodologyOut(MethodologyIn):
    id: str
    version: int


class MethodologyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    code: str | None = Field(default=None, min_length=2, max_length=64)
    severity_scale: list[ScaleItem] | None = None
    likelihood_scale: list[ScaleItem] | None = None
    bands: list[BandDef] | None = None

    model_config = ConfigDict(extra="forbid")


class RiskMapIn(BaseModel):
    methodology_id: str
    company_id: str
    site_id: str | None = None
    position_id: str | None = None
    document_pack_id: str | None = None

    model_config = ConfigDict(extra="forbid")


class RiskMapOut(BaseModel):
    id: str
    matrix: dict[str, object]
    methodology_id: str
    company_id: str
    site_id: str | None
    position_id: str | None
    document_pack_id: str | None


class AssessItemIn(BaseModel):
    hazard_code: str = Field(..., min_length=2, max_length=64)
    probability: int = Field(..., ge=1, le=5)
    severity: int = Field(..., ge=1, le=5)

    model_config = ConfigDict(extra="forbid")


class AssessIn(BaseModel):
    company_id: str | None = None
    place_id: str | None = None
    workplace_id: str | None = None
    position_id: str | None = None
    employee_id: str | None = None
    document_pack_id: str | None = None
    job_title: str | None = None
    methodology_id: str | None = None
    assessment_key: str | None = Field(default=None, max_length=64)
    assessment_version: int | None = Field(default=None, ge=1)
    hazard_code: str | None = Field(default=None, min_length=2, max_length=64)
    before: tuple[int, int] | None = None
    controls: list[str] = Field(default_factory=list)
    after: tuple[int, int] | None = None
    created_by: str | None = None
    items: list[AssessItemIn] | None = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("before", "after", mode="before")
    @classmethod
    def _validate_pair(cls, value: object) -> tuple[int, int] | None:
        if value is None:
            return None
        if isinstance(value, tuple):
            items = list(value)
        elif isinstance(value, list):
            items = value
        else:
            raise ValueError("Expected a sequence of two integers")
        if len(items) != 2:
            raise ValueError("Expected a pair of severity and likelihood values")
        normalized: list[int] = []
        for item in items:
            if isinstance(item, bool) or not isinstance(item, int):
                raise ValueError("Severity and likelihood must be integers in 1..5")
            if item < 1 or item > 5:
                raise ValueError("Severity and likelihood must be within 1..5")
            normalized.append(int(item))
        return cast(tuple[int, int], (normalized[0], normalized[1]))


class RiskAssessmentResponse(BaseModel):
    assessment_id: str
    assessment_key: str
    assessment_version: int
    risk_card_ids: list[str]
    action_plan_id: str | None


class RiskAssessmentItemOut(BaseModel):
    id: str
    hazard_id: str
    hazard_code: str
    hazard_title: str
    probability: int
    severity: int
    score: int
    level: str


class RiskAssessmentOut(BaseModel):
    id: str
    assessment_key: str
    assessment_version: int
    methodology_id: str | None
    methodology_version: int | None
    company_id: str | None
    place_id: str | None
    workplace_id: str | None
    position_id: str | None
    employee_id: str | None
    document_pack_id: str | None
    items: list[RiskAssessmentItemOut]
    risk_card_ids: list[str]
    action_plan_id: str | None


class RiskCardOut(BaseModel):
    id: str
    assessment_id: str
    company_id: str | None
    site_id: str | None
    workplace_id: str | None
    position_id: str | None
    employee_id: str | None
    methodology_id: str | None
    methodology_version: int | None
    summary: dict[str, object]


class ActionPlanItemOut(BaseModel):
    id: str
    hazard_id: str | None
    measure_text: str
    owner_role: str | None
    owner_id: str | None
    due_date: date | None
    status: str


class ActionPlanOut(BaseModel):
    id: str
    assessment_id: str
    status: str
    company_id: str | None
    site_id: str | None
    workplace_id: str | None
    position_id: str | None
    employee_id: str | None
    methodology_id: str | None
    methodology_version: int | None
    items: list[ActionPlanItemOut]
