"""Risk endpoints: register listing and risk engine helpers."""

from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, timedelta, timezone
from typing import Annotated, cast
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.dependencies import get_session, get_tenant_record
from app.api.helpers.etag import (
    apply_etag_response_headers,
    build_not_modified_headers,
    compute_list_etag,
)
from app.core.errors import api_problem_detail
from app.core.idempotency import compute_request_hash
from app.core.metrics import get_metrics
from app.core.security import AccessContext, AuthContext, abac, get_auth_ctx, rbac
from app.domains.risk import rebuild_matrix_from_methodology, recalc_risk_map, score_band
from app.models.models import (
    Company,
    DocumentPack,
    Person,
    Position,
    RiskMap,
    RiskMethodology,
    Site,
    Tenant,
    Workplace,
)
from app.models.risk import (
    Risk,
    RiskActionPlan,
    RiskActionPlanItem,
    RiskAssessment,
    RiskAssessmentItem,
    RiskCard,
    RiskControl,
    RiskHazard,
    RiskMatrixCell,
)
from app.schemas.risk import RiskListResponse
from app.services.events import EventType
from app.services.idempotency import IdempotencyService, normalize_idempotency_key
from app.services.outbox import OutboxService
from app.services.risk import RiskService

router = APIRouter(tags=["risks"])
engine_router = APIRouter(prefix="/risk", tags=["risk"])

logger = logging.getLogger("app.risk")

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[Tenant, Depends(get_tenant_record)]
EditorAccess = Annotated[AccessContext, Depends(rbac(["admin"]))]
AdminAccess = Annotated[AccessContext, Depends(rbac(["admin"]))]

_RISK_READ_ROLES = ["admin", "owner", "ot_specialist", "ot_pb_lead", "pb_engineer", "line_manager"]


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


@engine_router.post("/methodologies", response_model=MethodologyOut)
async def create_methodology(
    payload: MethodologyIn,
    session: SessionDep,
    tenant: TenantDep,
    _: AdminAccess,
) -> MethodologyOut:
    tenant_id = str(tenant.id)
    code = _slugify_code(payload.code or payload.name)
    existing = (
        await session.execute(
            select(RiskMethodology).where(
                RiskMethodology.tenant_id == tenant_id,
                (RiskMethodology.name == payload.name) | (RiskMethodology.code == code),
            )
        )
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, "Methodology name already exists")

    definition = {
        "severity_scale": [item.model_dump() for item in payload.severity_scale],
        "likelihood_scale": [item.model_dump() for item in payload.likelihood_scale],
        "bands": [band.model_dump() for band in payload.bands],
    }
    record = RiskMethodology(
        tenant_id=tenant_id,
        code=code,
        name=payload.name,
        definition=definition,
    )
    session.add(record)
    await session.flush()
    await session.commit()
    return MethodologyOut(
        id=record.id,
        code=record.code,
        name=record.name,
        severity_scale=definition.get("severity_scale", []),
        likelihood_scale=definition.get("likelihood_scale", []),
        bands=definition.get("bands", []),
        version=record.version,
    )


@engine_router.get("/methodologies", response_model=list[MethodologyOut])
async def list_methodologies(
    request: Request,
    response: Response,
    session: SessionDep,
    tenant: TenantDep,
    _: EditorAccess,
) -> list[MethodologyOut] | Response:
    tenant_id = str(tenant.id)
    records = list(
        (
            await session.execute(
                select(RiskMethodology).where(RiskMethodology.tenant_id == tenant_id)
            )
        )
        .scalars()
        .all()
    )
    etag = compute_list_etag(
        tenant_id=tenant_id,
        items=records,
        scalars=[("total", len(records)), ("kind", "methodologies")],
    )
    apply_etag_response_headers(response, etag)
    if request.headers.get("if-none-match") == etag:
        return Response(
            status_code=status.HTTP_304_NOT_MODIFIED,
            headers=build_not_modified_headers(etag),
        )
    result: list[MethodologyOut] = []
    for record in records:
        definition = record.definition or {}
        result.append(
            MethodologyOut(
                id=record.id,
                code=record.code,
                name=record.name,
                severity_scale=definition.get("severity_scale", []),
                likelihood_scale=definition.get("likelihood_scale", []),
                bands=definition.get("bands", []),
                version=record.version,
            )
        )
    return result


@engine_router.get("/methodologies/{methodology_id}", response_model=MethodologyOut)
async def get_methodology(
    methodology_id: str, session: SessionDep, tenant: TenantDep, _: EditorAccess
) -> MethodologyOut:
    tenant_id = str(tenant.id)
    record = await _get_tenant_entity(session, RiskMethodology, tenant_id, methodology_id)
    definition = record.definition or {}
    return MethodologyOut(
        id=record.id,
        code=record.code,
        name=record.name,
        severity_scale=definition.get("severity_scale", []),
        likelihood_scale=definition.get("likelihood_scale", []),
        bands=definition.get("bands", []),
        version=record.version,
    )


@engine_router.put("/methodologies/{methodology_id}", response_model=MethodologyOut)
async def update_methodology(
    methodology_id: str,
    payload: MethodologyUpdate,
    session: SessionDep,
    tenant: TenantDep,
    _: AdminAccess,
) -> MethodologyOut:
    tenant_id = str(tenant.id)
    record = await _get_tenant_entity(session, RiskMethodology, tenant_id, methodology_id)

    if payload.name and payload.name != record.name:
        duplicate = (
            await session.execute(
                select(RiskMethodology).where(
                    RiskMethodology.tenant_id == tenant_id,
                    RiskMethodology.name == payload.name,
                    RiskMethodology.id != record.id,
                )
            )
        ).scalar_one_or_none()
        if duplicate:
            raise HTTPException(status.HTTP_409_CONFLICT, "Methodology name already exists")
        record.name = payload.name

    if payload.code and payload.code != record.code:
        code = _slugify_code(payload.code)
        duplicate_code = (
            await session.execute(
                select(RiskMethodology).where(
                    RiskMethodology.tenant_id == tenant_id,
                    RiskMethodology.code == code,
                    RiskMethodology.id != record.id,
                )
            )
        ).scalar_one_or_none()
        if duplicate_code:
            raise HTTPException(status.HTTP_409_CONFLICT, "Methodology code already exists")
        record.code = code

    definition = record.definition or {}
    if payload.severity_scale is not None:
        definition["severity_scale"] = [item.model_dump() for item in payload.severity_scale]
    if payload.likelihood_scale is not None:
        definition["likelihood_scale"] = [item.model_dump() for item in payload.likelihood_scale]
    if payload.bands is not None:
        definition["bands"] = [band.model_dump() for band in payload.bands]
    record.definition = definition

    await session.flush()
    await session.commit()
    return MethodologyOut(
        id=record.id,
        code=record.code,
        name=record.name,
        severity_scale=definition.get("severity_scale", []),
        likelihood_scale=definition.get("likelihood_scale", []),
        bands=definition.get("bands", []),
        version=record.version,
    )


@engine_router.delete(
    "/methodologies/{methodology_id}",
    status_code=status.HTTP_200_OK,
)
async def delete_methodology(
    methodology_id: str, session: SessionDep, tenant: TenantDep, _: AdminAccess
) -> None:
    tenant_id = str(tenant.id)
    record = await _get_tenant_entity(session, RiskMethodology, tenant_id, methodology_id)
    await session.delete(record)
    await session.commit()
    return {"ok": True}


@engine_router.post("/hazards", status_code=status.HTTP_200_OK)
async def add_hazard(
    payload: HazardIn,
    session: SessionDep,
    tenant: TenantDep,
    _: EditorAccess,
) -> dict[str, str]:
    tenant_id = str(tenant.id)
    existing = (
        await session.execute(
            select(RiskHazard).where(
                RiskHazard.tenant_id == tenant_id,
                RiskHazard.code == payload.code,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Hazard code already exists")

    hazard = RiskHazard(
        tenant_id=tenant_id,
        code=payload.code,
        title=payload.title,
        module=payload.module,
        description=payload.description,
        recommended_measures=[
            measure.model_dump(mode="json") for measure in payload.recommended_measures
        ],
    )
    session.add(hazard)
    await session.flush()
    await session.commit()
    return {"id": hazard.id}


@engine_router.post("/controls", status_code=status.HTTP_200_OK)
async def add_control(
    payload: ControlIn,
    session: SessionDep,
    tenant: TenantDep,
    _: EditorAccess,
) -> dict[str, str]:
    tenant_id = str(tenant.id)
    existing = (
        await session.execute(
            select(RiskControl).where(
                RiskControl.tenant_id == tenant_id,
                RiskControl.code == payload.code,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Control code already exists")

    control = RiskControl(
        tenant_id=tenant_id,
        code=payload.code,
        title=payload.title,
        type=payload.type,
        description=payload.description,
    )
    session.add(control)
    await session.flush()
    await session.commit()
    return {"id": control.id}


@engine_router.put("/matrix", status_code=status.HTTP_200_OK)
async def set_matrix(
    payload: MatrixUp,
    session: SessionDep,
    tenant: TenantDep,
    _: AdminAccess,
) -> dict[str, int | bool]:
    tenant_id = str(tenant.id)
    cells: list[RiskMatrixCell]
    if payload.methodology_id and not payload.rows:
        methodology = await _get_tenant_entity(
            session, RiskMethodology, tenant_id, payload.methodology_id
        )
        cells = await rebuild_matrix_from_methodology(session, tenant_id, methodology)
    else:
        await session.execute(delete(RiskMatrixCell).where(RiskMatrixCell.tenant_id == tenant_id))
        cells = [
            RiskMatrixCell(
                tenant_id=tenant_id,
                severity=row.severity,
                likelihood=row.likelihood,
                score=row.score,
                band=row.band,
            )
            for row in payload.rows
        ]
        session.add_all(cells)
    await session.commit()
    return {"ok": True, "count": len(cells)}


@engine_router.post("/maps", response_model=RiskMapOut)
async def save_risk_map(
    payload: RiskMapIn,
    session: SessionDep,
    tenant: TenantDep,
    _: EditorAccess,
) -> RiskMapOut:
    tenant_id = str(tenant.id)
    methodology = await _get_tenant_entity(
        session, RiskMethodology, tenant_id, payload.methodology_id
    )
    await _get_tenant_entity(session, Company, tenant_id, payload.company_id)
    if payload.site_id:
        await _get_tenant_entity(session, Site, tenant_id, payload.site_id)
    if payload.position_id:
        await _get_tenant_entity(session, Position, tenant_id, payload.position_id)
    if payload.document_pack_id:
        await _get_tenant_entity(session, DocumentPack, tenant_id, payload.document_pack_id)

    matrix = await recalc_risk_map(
        session,
        tenant_id,
        methodology,
        company_id=payload.company_id,
        site_id=payload.site_id,
        position_id=payload.position_id,
        document_pack_id=payload.document_pack_id,
    )

    existing = (
        await session.execute(
            select(RiskMap).where(
                RiskMap.tenant_id == tenant_id,
                RiskMap.company_id == payload.company_id,
                RiskMap.site_id == payload.site_id,
                RiskMap.position_id == payload.position_id,
                RiskMap.methodology_id == payload.methodology_id,
            )
        )
    ).scalar_one_or_none()

    if existing:
        existing.matrix = matrix
        existing.recalculated_at = datetime.now(timezone.utc)
        target = existing
    else:
        target = RiskMap(
            tenant_id=tenant_id,
            methodology_id=payload.methodology_id,
            company_id=payload.company_id,
            site_id=payload.site_id,
            position_id=payload.position_id,
            document_pack_id=payload.document_pack_id,
            matrix=matrix,
            recalculated_at=datetime.now(timezone.utc),
        )
        session.add(target)

    await session.commit()
    return RiskMapOut(
        id=target.id,
        matrix=matrix,
        methodology_id=payload.methodology_id,
        company_id=payload.company_id,
        site_id=payload.site_id,
        position_id=payload.position_id,
        document_pack_id=payload.document_pack_id,
    )


@engine_router.get("/maps", response_model=list[RiskMapOut])
async def list_risk_maps(
    request: Request,
    response: Response,
    session: SessionDep,
    tenant: TenantDep,
    _: EditorAccess,
    company_id: str = Query(..., alias="company_id"),
    site_id: str | None = Query(default=None, alias="site_id"),
    position_id: str | None = Query(default=None, alias="position_id"),
    methodology_id: str | None = Query(default=None, alias="methodology_id"),
) -> list[RiskMapOut] | Response:
    tenant_id = str(tenant.id)
    await _get_tenant_entity(session, Company, tenant_id, company_id)
    stmt = select(RiskMap).where(RiskMap.tenant_id == tenant_id, RiskMap.company_id == company_id)
    if site_id:
        stmt = stmt.where(RiskMap.site_id == site_id)
    if position_id:
        stmt = stmt.where(RiskMap.position_id == position_id)
    if methodology_id:
        stmt = stmt.where(RiskMap.methodology_id == methodology_id)

    records = list((await session.execute(stmt)).scalars().all())
    etag = compute_list_etag(
        tenant_id=tenant_id,
        items=records,
        scalars=[
            ("total", len(records)),
            ("kind", "maps"),
            ("company", company_id),
            ("site", site_id or ""),
            ("position", position_id or ""),
            ("methodology", methodology_id or ""),
        ],
    )
    apply_etag_response_headers(response, etag)
    if request.headers.get("if-none-match") == etag:
        return Response(
            status_code=status.HTTP_304_NOT_MODIFIED,
            headers=build_not_modified_headers(etag),
        )
    return [
        RiskMapOut(
            id=record.id,
            matrix=record.matrix,
            methodology_id=record.methodology_id,
            company_id=record.company_id,
            site_id=record.site_id,
            position_id=record.position_id,
            document_pack_id=record.document_pack_id,
        )
        for record in records
    ]


@engine_router.post(
    "/assess", response_model=RiskAssessmentResponse, status_code=status.HTTP_200_OK
)
async def assess(
    payload: AssessIn,
    request: Request,
    response: Response,
    session: SessionDep,
    tenant: TenantDep,
    _: EditorAccess,
    auth: AuthContext = Depends(get_auth_ctx),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> RiskAssessmentResponse:
    tenant_id = str(tenant.id)
    idempotency: IdempotencyService | None = None
    idempotency_record = None
    if idempotency_key is not None:
        normalized_key = normalize_idempotency_key(idempotency_key)
        idem_state = getattr(request.state, "idempotency", {})
        request_hash = idem_state.get("fingerprint")
        if request_hash is None:
            request_hash = compute_request_hash(payload)
            request.state.idempotency = {"key": normalized_key, "fingerprint": request_hash}
        idempotency = IdempotencyService(
            session=session,
            tenant_id=tenant_id,
            endpoint="risk.assess",
        )
        idempotency_record, created_record = await idempotency.acquire(
            key=normalized_key,
            request_hash=request_hash,
            method=request.method.upper(),
            path=request.url.path,
        )
        if not created_record:
            return await idempotency.respond_from_store(
                idempotency_record, model=RiskAssessmentResponse, response=response
            )

    if payload.company_id:
        await _get_tenant_entity(session, Company, tenant_id, payload.company_id)
    if payload.place_id:
        await _get_tenant_entity(session, Site, tenant_id, payload.place_id)
    if payload.workplace_id:
        await _get_tenant_entity(session, Workplace, tenant_id, payload.workplace_id)
    if payload.position_id:
        await _get_tenant_entity(session, Position, tenant_id, payload.position_id)
    if payload.employee_id:
        await _get_tenant_entity(session, Person, tenant_id, payload.employee_id)
    if payload.document_pack_id:
        await _get_tenant_entity(session, DocumentPack, tenant_id, payload.document_pack_id)

    if payload.items:
        items_payload = payload.items
    else:
        if payload.hazard_code is None or payload.before is None:
            raise _risk_bad_request("hazard_code and before are required")
        severity_before, likelihood_before = payload.before
        items_payload = [
            AssessItemIn(
                hazard_code=payload.hazard_code,
                probability=likelihood_before,
                severity=severity_before,
            )
        ]

    hazard_codes = [item.hazard_code for item in items_payload]
    hazards = (
        (
            await session.execute(
                select(RiskHazard).where(
                    RiskHazard.tenant_id == tenant_id,
                    RiskHazard.code.in_(hazard_codes),
                )
            )
        )
        .scalars()
        .all()
    )
    hazard_lookup = {hazard.code: hazard for hazard in hazards}
    missing = [code for code in hazard_codes if code not in hazard_lookup]
    if missing:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, f"Hazard not found: {', '.join(sorted(missing))}"
        )

    if payload.methodology_id:
        methodology = await _get_tenant_entity(
            session, RiskMethodology, tenant_id, payload.methodology_id
        )
    else:
        methodology = await _get_or_create_default_methodology(session, tenant_id)
    definition = methodology.definition or {}

    assessment_key = payload.assessment_key or str(uuid4())
    assessment_version = payload.assessment_version or 1
    if payload.assessment_key:
        existing_assessment = (
            await session.execute(
                select(RiskAssessment)
                .where(
                    RiskAssessment.tenant_id == tenant_id,
                    RiskAssessment.assessment_key == assessment_key,
                    RiskAssessment.assessment_version == assessment_version,
                )
                .options(selectinload(RiskAssessment.risk_cards))
                .options(selectinload(RiskAssessment.action_plan))
            )
        ).scalar_one_or_none()
        if existing_assessment is not None:
            cards = existing_assessment.risk_cards
            plan = existing_assessment.action_plan
            response_payload = RiskAssessmentResponse(
                assessment_id=existing_assessment.id,
                assessment_key=existing_assessment.assessment_key,
                assessment_version=existing_assessment.assessment_version,
                risk_card_ids=[card.id for card in cards],
                action_plan_id=plan.id if plan else None,
            )
            if idempotency and idempotency_record:
                await idempotency.store_success(
                    idempotency_record,
                    status_code=status.HTTP_200_OK,
                    body=response_payload.model_dump(mode="json"),
                )
            return response_payload

    before_pair = payload.before
    if before_pair is None:
        before_pair = (items_payload[0].severity, items_payload[0].probability)
    severity_before, likelihood_before = before_pair
    score_before, band_before = await score_band(
        session, tenant_id, severity_before, likelihood_before
    )

    if payload.items is None:
        if payload.after is not None:
            severity_after, likelihood_after = payload.after
        else:
            severity_after, likelihood_after = severity_before, max(1, likelihood_before - 1)
    else:
        severity_after, likelihood_after = severity_before, likelihood_before
    score_after, band_after = await score_band(session, tenant_id, severity_after, likelihood_after)

    controls_json = json.dumps(payload.controls, ensure_ascii=False)
    created_by = payload.created_by or auth.sub
    controls_lookup = await _resolve_controls(
        session, tenant_id=tenant_id, control_codes=payload.controls
    )
    control_steps: list[dict[str, object]] = []
    for code in payload.controls:
        control = controls_lookup.get(code)
        if control is None:
            control_steps.append(
                {
                    "code": code,
                    "title": code,
                    "type": "org",
                    "description": None,
                    "status": "planned",
                    "missing": True,
                }
            )
            continue
        control_steps.append(
            {
                "code": control.code,
                "title": control.title,
                "type": control.type,
                "description": control.description,
                "status": "planned",
            }
        )

    first_hazard = hazard_lookup[items_payload[0].hazard_code]
    assessment = RiskAssessment(
        tenant_id=tenant_id,
        assessment_key=assessment_key,
        assessment_version=assessment_version,
        methodology_id=methodology.id,
        methodology_version=methodology.version,
        company_id=payload.company_id,
        place_id=payload.place_id,
        workplace_id=payload.workplace_id,
        position_id=payload.position_id,
        employee_id=payload.employee_id,
        document_pack_id=payload.document_pack_id,
        job_title=payload.job_title,
        hazard_id=first_hazard.id,
        severity_before=severity_before,
        likelihood_before=likelihood_before,
        score_before=score_before,
        band_before=band_before,
        controls=controls_json,
        risk_card=None,
        severity_after=severity_after,
        likelihood_after=likelihood_after,
        score_after=score_after,
        band_after=band_after,
        created_by=created_by,
    )
    session.add(assessment)
    await session.flush()

    item_rows: list[RiskAssessmentItem] = []
    item_payloads: list[dict[str, object]] = []
    for item in items_payload:
        hazard = hazard_lookup[item.hazard_code]
        score = int(item.probability) * int(item.severity)
        level = _band_from_definition(definition, score)
        item_rows.append(
            RiskAssessmentItem(
                tenant_id=tenant_id,
                assessment_id=assessment.id,
                hazard_id=hazard.id,
                probability=item.probability,
                severity=item.severity,
                score=score,
                level=level,
                methodology_id=methodology.id,
                methodology_version=methodology.version,
            )
        )
        item_payloads.append(
            {
                "hazard_id": hazard.id,
                "hazard_code": hazard.code,
                "hazard_title": hazard.title,
                "probability": item.probability,
                "severity": item.severity,
                "score": score,
                "level": level,
            }
        )
    session.add_all(item_rows)

    counts_by_level: dict[str, int] = {}
    for payload_item in item_payloads:
        level = cast(str, payload_item["level"])
        counts_by_level[level] = counts_by_level.get(level, 0) + 1
    sorted_items = sorted(
        item_payloads,
        key=lambda entry: (-int(entry["score"]), str(entry["hazard_code"])),
    )

    summary = {
        "assessment_id": assessment.id,
        "methodology": {
            "id": str(methodology.id),
            "version": methodology.version,
        },
        "scope": {
            "company_id": payload.company_id,
            "place_id": payload.place_id,
            "workplace_id": payload.workplace_id,
            "position_id": payload.position_id,
            "employee_id": payload.employee_id,
            "document_pack_id": payload.document_pack_id,
        },
        "counts_by_level": counts_by_level,
        "items": sorted_items,
    }

    risk_card = RiskCard(
        tenant_id=tenant_id,
        assessment_id=assessment.id,
        company_id=payload.company_id,
        site_id=payload.place_id,
        workplace_id=payload.workplace_id,
        position_id=payload.position_id,
        employee_id=payload.employee_id,
        methodology_id=methodology.id,
        methodology_version=methodology.version,
        summary=summary,
    )
    session.add(risk_card)

    action_plan = RiskActionPlan(
        tenant_id=tenant_id,
        assessment_id=assessment.id,
        company_id=payload.company_id,
        site_id=payload.place_id,
        workplace_id=payload.workplace_id,
        position_id=payload.position_id,
        employee_id=payload.employee_id,
        methodology_id=methodology.id,
        methodology_version=methodology.version,
        status="open",
    )
    session.add(action_plan)
    await session.flush()

    created_at = assessment.created_at
    plan_items: list[RiskActionPlanItem] = []
    for item in sorted_items:
        hazard_id = cast(str, item["hazard_id"])
        hazard = hazard_lookup[cast(str, item["hazard_code"])]
        measures = list(hazard.recommended_measures or [])
        if not measures and control_steps:
            measures = [
                {
                    "text": step.get("title") or step.get("code") or str(step),
                    "owner_role": None,
                    "owner_id": None,
                    "due_in_days": 30,
                }
                for step in control_steps
            ]
        if not measures:
            measures = [
                {
                    "text": f"Review hazard: {hazard.title}",
                    "owner_role": None,
                    "owner_id": None,
                    "due_in_days": 30,
                }
            ]
        for measure in sorted(measures, key=lambda entry: str(entry.get("text", ""))):
            due_in_days = measure.get("due_in_days")
            due_date: date | None = None
            if isinstance(due_in_days, int):
                due_date = (created_at + timedelta(days=due_in_days)).date()
            plan_items.append(
                RiskActionPlanItem(
                    tenant_id=tenant_id,
                    plan_id=action_plan.id,
                    assessment_id=assessment.id,
                    hazard_id=hazard_id,
                    measure_text=str(measure.get("text") or ""),
                    owner_role=cast(str | None, measure.get("owner_role")),
                    owner_id=cast(str | None, measure.get("owner_id")),
                    due_date=due_date,
                    status="planned",
                    methodology_id=methodology.id,
                    methodology_version=methodology.version,
                )
            )
    session.add_all(plan_items)

    outbox = OutboxService(session)
    await outbox.enqueue(
        tenant_id=tenant_id,
        event_type=EventType.RISK_ASSESSED.value,
        payload={
            "tenant_id": tenant_id,
            "actor_id": created_by,
            "occurred_at": assessment.created_at,
            "risk_assessment_id": assessment.id,
            "hazard_code": first_hazard.code,
            "company_id": payload.company_id,
            "place_id": payload.place_id,
            "position_id": payload.position_id,
            "document_pack_id": payload.document_pack_id,
            "before": {
                "severity": severity_before,
                "likelihood": likelihood_before,
                "score": score_before,
                "band": band_before,
            },
            "after": {
                "severity": severity_after,
                "likelihood": likelihood_after,
                "score": score_after,
                "band": band_after,
            },
            "controls": control_steps,
            "action_plan": {
                "id": action_plan.id,
                "risk_card_ids": [risk_card.id],
                "items": [
                    {
                        "id": plan_item.id,
                        "hazard_id": plan_item.hazard_id,
                        "measure_text": plan_item.measure_text,
                        "due_date": plan_item.due_date,
                        "status": plan_item.status,
                    }
                    for plan_item in plan_items
                ],
            },
        },
    )

    metrics = get_metrics()
    metrics.risk_assessment_total.inc()
    metrics.risk_cards_created_total.inc()
    metrics.action_plan_items_created_total.inc(len(plan_items))

    await session.commit()

    response_payload = RiskAssessmentResponse(
        assessment_id=assessment.id,
        assessment_key=assessment.assessment_key,
        assessment_version=assessment.assessment_version,
        risk_card_ids=[risk_card.id],
        action_plan_id=action_plan.id,
    )
    if idempotency and idempotency_record:
        await idempotency.store_success(
            idempotency_record,
            status_code=status.HTTP_200_OK,
            body=response_payload.model_dump(mode="json"),
        )
    logger.info(
        "risk.assessment.completed",
        extra={
            "assessment_id": assessment.id,
            "tenant_id": tenant_id,
            "scope": {
                "company_id": payload.company_id,
                "place_id": payload.place_id,
                "workplace_id": payload.workplace_id,
                "position_id": payload.position_id,
                "employee_id": payload.employee_id,
            },
            "methodology_version": methodology.version,
        },
    )
    return response_payload


@engine_router.get("/assessments/{assessment_id}", response_model=RiskAssessmentOut)
async def get_assessment(
    assessment_id: str,
    session: SessionDep,
    tenant: TenantDep,
    _: EditorAccess,
) -> RiskAssessmentOut:
    tenant_id = str(tenant.id)
    stmt = (
        select(RiskAssessment)
        .where(RiskAssessment.tenant_id == tenant_id, RiskAssessment.id == assessment_id)
        .options(selectinload(RiskAssessment.items).selectinload(RiskAssessmentItem.hazard))
        .options(selectinload(RiskAssessment.risk_cards))
        .options(selectinload(RiskAssessment.action_plan).selectinload(RiskActionPlan.items))
    )
    assessment = (await session.execute(stmt)).scalar_one_or_none()
    if assessment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Assessment not found")

    items = sorted(
        assessment.items,
        key=lambda item: (-item.score, item.hazard.code if item.hazard else ""),
    )
    item_payloads = [
        RiskAssessmentItemOut(
            id=item.id,
            hazard_id=item.hazard_id,
            hazard_code=item.hazard.code if item.hazard else "",
            hazard_title=item.hazard.title if item.hazard else "",
            probability=item.probability,
            severity=item.severity,
            score=item.score,
            level=item.level,
        )
        for item in items
    ]
    risk_card_ids = [card.id for card in assessment.risk_cards]
    plan = assessment.action_plan
    return RiskAssessmentOut(
        id=assessment.id,
        assessment_key=assessment.assessment_key,
        assessment_version=assessment.assessment_version,
        methodology_id=assessment.methodology_id,
        methodology_version=assessment.methodology_version,
        company_id=assessment.company_id,
        place_id=assessment.place_id,
        workplace_id=assessment.workplace_id,
        position_id=assessment.position_id,
        employee_id=assessment.employee_id,
        document_pack_id=assessment.document_pack_id,
        items=item_payloads,
        risk_card_ids=risk_card_ids,
        action_plan_id=plan.id if plan else None,
    )


@engine_router.get("/cards", response_model=list[RiskCardOut])
async def list_risk_cards(
    request: Request,
    response: Response,
    session: SessionDep,
    tenant: TenantDep,
    _: EditorAccess,
    assessment_id: str | None = Query(default=None, alias="assessment_id"),
    company_id: str | None = Query(default=None, alias="company_id"),
    site_id: str | None = Query(default=None, alias="site_id"),
    workplace_id: str | None = Query(default=None, alias="workplace_id"),
    position_id: str | None = Query(default=None, alias="position_id"),
    employee_id: str | None = Query(default=None, alias="employee_id"),
) -> list[RiskCardOut] | Response:
    tenant_id = str(tenant.id)
    stmt = select(RiskCard).where(RiskCard.tenant_id == tenant_id)
    if assessment_id:
        stmt = stmt.where(RiskCard.assessment_id == assessment_id)
    if company_id:
        stmt = stmt.where(RiskCard.company_id == company_id)
    if site_id:
        stmt = stmt.where(RiskCard.site_id == site_id)
    if workplace_id:
        stmt = stmt.where(RiskCard.workplace_id == workplace_id)
    if position_id:
        stmt = stmt.where(RiskCard.position_id == position_id)
    if employee_id:
        stmt = stmt.where(RiskCard.employee_id == employee_id)
    records = list(
        (await session.execute(stmt.order_by(RiskCard.created_at.desc()))).scalars().all()
    )
    etag = compute_list_etag(
        tenant_id=tenant_id,
        items=records,
        scalars=[
            ("total", len(records)),
            ("kind", "cards"),
            ("assessment", assessment_id or ""),
            ("company", company_id or ""),
            ("site", site_id or ""),
            ("workplace", workplace_id or ""),
            ("position", position_id or ""),
            ("employee", employee_id or ""),
        ],
    )
    apply_etag_response_headers(response, etag)
    if request.headers.get("if-none-match") == etag:
        return Response(
            status_code=status.HTTP_304_NOT_MODIFIED,
            headers=build_not_modified_headers(etag),
        )
    return [
        RiskCardOut(
            id=record.id,
            assessment_id=record.assessment_id,
            company_id=record.company_id,
            site_id=record.site_id,
            workplace_id=record.workplace_id,
            position_id=record.position_id,
            employee_id=record.employee_id,
            methodology_id=record.methodology_id,
            methodology_version=record.methodology_version,
            summary=record.summary,
        )
        for record in records
    ]


@engine_router.get("/action-plans", response_model=list[ActionPlanOut])
async def list_action_plans(
    request: Request,
    response: Response,
    session: SessionDep,
    tenant: TenantDep,
    _: EditorAccess,
    assessment_id: str | None = Query(default=None, alias="assessment_id"),
    company_id: str | None = Query(default=None, alias="company_id"),
    site_id: str | None = Query(default=None, alias="site_id"),
    workplace_id: str | None = Query(default=None, alias="workplace_id"),
    position_id: str | None = Query(default=None, alias="position_id"),
    employee_id: str | None = Query(default=None, alias="employee_id"),
) -> list[ActionPlanOut] | Response:
    tenant_id = str(tenant.id)
    stmt = (
        select(RiskActionPlan)
        .where(RiskActionPlan.tenant_id == tenant_id)
        .options(selectinload(RiskActionPlan.items))
    )
    if assessment_id:
        stmt = stmt.where(RiskActionPlan.assessment_id == assessment_id)
    if company_id:
        stmt = stmt.where(RiskActionPlan.company_id == company_id)
    if site_id:
        stmt = stmt.where(RiskActionPlan.site_id == site_id)
    if workplace_id:
        stmt = stmt.where(RiskActionPlan.workplace_id == workplace_id)
    if position_id:
        stmt = stmt.where(RiskActionPlan.position_id == position_id)
    if employee_id:
        stmt = stmt.where(RiskActionPlan.employee_id == employee_id)

    records = list(
        (await session.execute(stmt.order_by(RiskActionPlan.created_at.desc()))).scalars().all()
    )
    etag = compute_list_etag(
        tenant_id=tenant_id,
        items=records,
        scalars=[
            ("total", len(records)),
            ("kind", "action_plans"),
            ("assessment", assessment_id or ""),
            ("company", company_id or ""),
            ("site", site_id or ""),
            ("workplace", workplace_id or ""),
            ("position", position_id or ""),
            ("employee", employee_id or ""),
        ],
    )
    apply_etag_response_headers(response, etag)
    if request.headers.get("if-none-match") == etag:
        return Response(
            status_code=status.HTTP_304_NOT_MODIFIED,
            headers=build_not_modified_headers(etag),
        )
    result: list[ActionPlanOut] = []
    for record in records:
        items = sorted(record.items, key=lambda item: (item.due_date or date.min, item.id))
        result.append(
            ActionPlanOut(
                id=record.id,
                assessment_id=record.assessment_id,
                status=record.status,
                company_id=record.company_id,
                site_id=record.site_id,
                workplace_id=record.workplace_id,
                position_id=record.position_id,
                employee_id=record.employee_id,
                methodology_id=record.methodology_id,
                methodology_version=record.methodology_version,
                items=[
                    ActionPlanItemOut(
                        id=item.id,
                        hazard_id=item.hazard_id,
                        measure_text=item.measure_text,
                        owner_role=item.owner_role,
                        owner_id=item.owner_id,
                        due_date=item.due_date,
                        status=item.status,
                    )
                    for item in items
                ],
            )
        )
    return result


@router.get("/risks", response_model=RiskListResponse)
async def list_risks(
    session: SessionDep,
    tenant: TenantDep,
    access: RiskReadAccess,
    site_id: str | None = Query(default=None, alias="site_id"),
    risk_level: str | None = Query(default=None, alias="risk_level"),
) -> RiskListResponse:
    if site_id:
        try:
            await RiskService.ensure_site_belongs_to_tenant(session, tenant, site_id)
        except LookupError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
        if site_id:
            site = await session.get(Site, site_id)
            if site is not None:
                access.ensure_site_access(site_id, site.company_id, action="read risks")

    if risk_level:
        access.ensure_risk_access(risk_level=risk_level, action="read risks")

    risks, report = await RiskService.list_by_site(session, tenant, site_id)
    if risk_level:
        try:
            minimum, maximum = _risk_level_filter(risk_level)
        except ValueError as exc:
            raise _risk_unprocessable(str(exc)) from exc
        filtered: list[Risk] = []
        for risk in risks:
            if minimum is not None and risk.level < minimum:
                continue
            if maximum is not None and risk.level > maximum:
                continue
            filtered.append(risk)
        risks = filtered
    return RiskListResponse.from_entities(risks, report)


router.include_router(engine_router)
