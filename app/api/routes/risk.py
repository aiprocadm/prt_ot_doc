"""Risk endpoints: register listing and risk engine helpers."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.core.security import AccessContext, AuthContext, get_auth_ctx, rbac
from app.domains.risk import recalc_risk_map, rebuild_matrix_from_methodology, score_band
from app.models.models import (
    Company,
    DocumentPack,
    Position,
    RiskMap,
    RiskMethodology,
    Site,
    Tenant,
)
from app.models.risk import (
    Risk,
    RiskAssessment,
    RiskControl,
    RiskHazard,
    RiskMatrixCell,
)
from app.schemas.risk import RiskListResponse
from app.services.risk import RiskService
from app.services.outbox import OutboxService

router = APIRouter(tags=["risks"])
engine_router = APIRouter(prefix="/risk", tags=["risk"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[Tenant, Depends(get_tenant_record)]
EditorAccess = Annotated[AccessContext, Depends(rbac(["admin"]))]
AdminAccess = Annotated[AccessContext, Depends(rbac(["admin"]))]


async def _get_tenant_entity(
    session: AsyncSession, model: type, tenant_id: str, entity_id: str
):
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


def _build_action_plan(
    *,
    hazard: RiskHazard,
    controls: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "hazard_code": hazard.code,
        "steps": controls,
    }


def _build_risk_card(
    *,
    hazard: RiskHazard,
    before: dict[str, object],
    after: dict[str, object],
    controls: list[dict[str, object]],
    action_plan: dict[str, object],
) -> dict[str, object]:
    return {
        "hazard": {
            "code": hazard.code,
            "title": hazard.title,
            "module": hazard.module,
            "description": hazard.description,
        },
        "before": before,
        "after": after,
        "controls": controls,
        "action_plan": action_plan,
    }


class HazardIn(BaseModel):
    code: str = Field(..., min_length=2, max_length=64)
    title: str = Field(..., min_length=2, max_length=256)
    module: str = Field(default="ot", pattern=r"^(ot|pb|prom|eco|siz|common)$")
    description: str | None = None

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
    severity_scale: list[ScaleItem] = Field(default_factory=list)
    likelihood_scale: list[ScaleItem] = Field(default_factory=list)
    bands: list[BandDef] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class MethodologyOut(MethodologyIn):
    id: str


class MethodologyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
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


class AssessIn(BaseModel):
    company_id: str | None = None
    place_id: str | None = None
    position_id: str | None = None
    document_pack_id: str | None = None
    job_title: str | None = None
    hazard_code: str = Field(..., min_length=2, max_length=64)
    before: tuple[int, int]
    controls: list[str] = Field(default_factory=list)
    after: tuple[int, int] | None = None
    created_by: str | None = None

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


@engine_router.post("/methodologies", response_model=MethodologyOut)
async def create_methodology(
    payload: MethodologyIn,
    session: SessionDep,
    tenant: TenantDep,
    _: AdminAccess,
) -> MethodologyOut:
    tenant_id = str(tenant.id)
    existing = (
        await session.execute(
            select(RiskMethodology).where(
                RiskMethodology.tenant_id == tenant_id,
                RiskMethodology.name == payload.name,
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
        name=payload.name,
        definition=definition,
    )
    session.add(record)
    await session.flush()
    await session.commit()
    return MethodologyOut(id=record.id, **payload.model_dump())


@engine_router.get("/methodologies", response_model=list[MethodologyOut])
async def list_methodologies(
    session: SessionDep, tenant: TenantDep, _: EditorAccess
) -> list[MethodologyOut]:
    tenant_id = str(tenant.id)
    records = (
        await session.execute(
            select(RiskMethodology).where(RiskMethodology.tenant_id == tenant_id)
        )
    ).scalars()
    result: list[MethodologyOut] = []
    for record in records:
        definition = record.definition or {}
        result.append(
            MethodologyOut(
                id=record.id,
                name=record.name,
                severity_scale=definition.get("severity_scale", []),
                likelihood_scale=definition.get("likelihood_scale", []),
                bands=definition.get("bands", []),
            )
        )
    return result


@engine_router.get("/methodologies/{methodology_id}", response_model=MethodologyOut)
async def get_methodology(
    methodology_id: str, session: SessionDep, tenant: TenantDep, _: EditorAccess
) -> MethodologyOut:
    tenant_id = str(tenant.id)
    record = await _get_tenant_entity(
        session, RiskMethodology, tenant_id, methodology_id
    )
    definition = record.definition or {}
    return MethodologyOut(
        id=record.id,
        name=record.name,
        severity_scale=definition.get("severity_scale", []),
        likelihood_scale=definition.get("likelihood_scale", []),
        bands=definition.get("bands", []),
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
    record = await _get_tenant_entity(
        session, RiskMethodology, tenant_id, methodology_id
    )

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
        name=record.name,
        severity_scale=definition.get("severity_scale", []),
        likelihood_scale=definition.get("likelihood_scale", []),
        bands=definition.get("bands", []),
    )


@engine_router.delete(
    "/methodologies/{methodology_id}",
    status_code=status.HTTP_200_OK,
)
async def delete_methodology(
    methodology_id: str, session: SessionDep, tenant: TenantDep, _: AdminAccess
) -> None:
    tenant_id = str(tenant.id)
    record = await _get_tenant_entity(
        session, RiskMethodology, tenant_id, methodology_id
    )
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
        await session.execute(
            delete(RiskMatrixCell).where(RiskMatrixCell.tenant_id == tenant_id)
        )
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
        await _get_tenant_entity(
            session, DocumentPack, tenant_id, payload.document_pack_id
        )

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
    session: SessionDep,
    tenant: TenantDep,
    _: EditorAccess,
    company_id: str = Query(..., alias="company_id"),
    site_id: str | None = Query(default=None, alias="site_id"),
    position_id: str | None = Query(default=None, alias="position_id"),
    methodology_id: str | None = Query(default=None, alias="methodology_id"),
) -> list[RiskMapOut]:
    tenant_id = str(tenant.id)
    await _get_tenant_entity(session, Company, tenant_id, company_id)
    stmt = select(RiskMap).where(
        RiskMap.tenant_id == tenant_id, RiskMap.company_id == company_id
    )
    if site_id:
        stmt = stmt.where(RiskMap.site_id == site_id)
    if position_id:
        stmt = stmt.where(RiskMap.position_id == position_id)
    if methodology_id:
        stmt = stmt.where(RiskMap.methodology_id == methodology_id)

    records = (await session.execute(stmt)).scalars().all()
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


@engine_router.post("/assess", status_code=status.HTTP_200_OK)
async def assess(
    payload: AssessIn,
    session: SessionDep,
    tenant: TenantDep,
    _: EditorAccess,
    auth: AuthContext = Depends(get_auth_ctx),
) -> dict[str, object]:
    tenant_id = str(tenant.id)
    hazard = (
        await session.execute(
            select(RiskHazard).where(
                RiskHazard.tenant_id == tenant_id,
                RiskHazard.code == payload.hazard_code,
            )
        )
    ).scalar_one_or_none()
    if hazard is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Hazard not found")

    if payload.company_id:
        await _get_tenant_entity(session, Company, tenant_id, payload.company_id)
    if payload.place_id:
        await _get_tenant_entity(session, Site, tenant_id, payload.place_id)
    if payload.position_id:
        await _get_tenant_entity(session, Position, tenant_id, payload.position_id)
    if payload.document_pack_id:
        await _get_tenant_entity(
            session, DocumentPack, tenant_id, payload.document_pack_id
        )

    before_pair = payload.before
    if before_pair is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "before is required")
    severity_before, likelihood_before = before_pair
    score_before, band_before = await score_band(
        session, tenant_id, severity_before, likelihood_before
    )

    if payload.after is not None:
        severity_after, likelihood_after = payload.after
    else:
        severity_after, likelihood_after = severity_before, max(1, likelihood_before - 1)
    score_after, band_after = await score_band(
        session, tenant_id, severity_after, likelihood_after
    )

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
    if not control_steps:
        control_steps = [
            {
                "code": f"review-{hazard.code}",
                "title": f"Review hazard: {hazard.title}",
                "type": "org",
                "description": hazard.description,
                "status": "planned",
            }
        ]

    before_payload = {
        "severity": severity_before,
        "likelihood": likelihood_before,
        "score": score_before,
        "band": band_before,
    }
    after_payload = {
        "severity": severity_after,
        "likelihood": likelihood_after,
        "score": score_after,
        "band": band_after,
    }
    action_plan = _build_action_plan(hazard=hazard, controls=control_steps)
    risk_card = _build_risk_card(
        hazard=hazard,
        before=before_payload,
        after=after_payload,
        controls=control_steps,
        action_plan=action_plan,
    )

    assessment = RiskAssessment(
        tenant_id=tenant_id,
        company_id=payload.company_id,
        place_id=payload.place_id,
        position_id=payload.position_id,
        document_pack_id=payload.document_pack_id,
        job_title=payload.job_title,
        hazard_id=hazard.id,
        severity_before=severity_before,
        likelihood_before=likelihood_before,
        score_before=score_before,
        band_before=band_before,
        controls=controls_json,
        action_plan=action_plan,
        risk_card=risk_card,
        severity_after=severity_after,
        likelihood_after=likelihood_after,
        score_after=score_after,
        band_after=band_after,
        created_by=created_by,
    )
    session.add(assessment)
    await session.flush()
    outbox = OutboxService(session)
    await outbox.enqueue(
        tenant_id=tenant_id,
        event_type="RiskAssessed",
        payload={
            "assessment_id": assessment.id,
            "hazard_code": hazard.code,
            "company_id": payload.company_id,
            "place_id": payload.place_id,
            "position_id": payload.position_id,
            "document_pack_id": payload.document_pack_id,
            "before": before_payload,
            "after": after_payload,
            "controls": control_steps,
            "action_plan": action_plan,
        },
    )
    await session.commit()

    return {
        "id": assessment.id,
        "hazard": {"code": payload.hazard_code, "title": hazard.title},
        "before": before_payload,
        "after": after_payload,
        "controls": payload.controls,
        "action_plan": action_plan,
        "risk_card": risk_card,
    }


@router.get("/risks", response_model=RiskListResponse)
async def list_risks(
    session: SessionDep,
    tenant: TenantDep,
    site_id: str | None = Query(default=None, alias="site_id"),
) -> RiskListResponse:
    if site_id:
        try:
            await RiskService.ensure_site_belongs_to_tenant(session, tenant, site_id)
        except LookupError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc

    risks, report = await RiskService.list_by_site(session, tenant, site_id)
    return RiskListResponse.from_entities(risks, report)


router.include_router(engine_router)
