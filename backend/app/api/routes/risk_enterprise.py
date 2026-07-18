from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.core.audit_decorator import audit_operation
from app.models.models import Tenant
from app.models.safety_core import (
    RiskMapItem,
    RiskMapItemMeasure,
    RiskMeasure,
    SafetyRiskMap,
    SafetyRiskMethodology,
)
from app.models.safety_ops import CorrectiveAction, IncidentCase
from app.modules.rbac_abac import require_permission
from app.modules.risk.services import RiskCalculationService, RiskMeasureService

router = APIRouter(prefix="/risk/advanced", tags=["risk-advanced"])

_MethodologiesReadDep = Depends(require_permission("risk_methodologies.read"))
_MethodologiesWriteDep = Depends(require_permission("risk_methodologies.update"))
_MapsReadDep = Depends(require_permission("risk_maps.read"))
_MapsWriteDep = Depends(require_permission("risk_maps.update"))


class MethodologyCreate(BaseModel):
    code: str
    name: str
    type: str = "matrix"
    status: str = "draft"
    version_no: int = 1
    formula_json: dict = Field(default_factory=dict)
    scale_json: dict = Field(default_factory=dict)


class RiskMapCreate(BaseModel):
    entity_type: str
    entity_id: str
    risk_methodology_id: str
    source: str | None = None


class MapItemUpsert(BaseModel):
    hazard_id: str
    probability_value: float
    severity_value: float
    exposure_value: float | None = None
    measure_ids: list[str] = Field(default_factory=list)


class MethodologyClone(BaseModel):
    version_no: int | None = None
    name: str | None = None


@router.get("/methodologies")
async def list_methodologies(
    tenant: Tenant = Depends(get_tenant_record),
    session: AsyncSession = Depends(get_session),
    __: Any = _MethodologiesReadDep,
):
    rows = (
        (
            await session.execute(
                select(SafetyRiskMethodology)
                .where(
                    SafetyRiskMethodology.tenant_id == tenant.id,
                    SafetyRiskMethodology.deleted_at.is_(None),
                )
                .order_by(SafetyRiskMethodology.code, SafetyRiskMethodology.version_no.desc())
            )
        )
        .scalars()
        .all()
    )
    return {"items": rows, "total": len(rows)}


@router.post("/methodologies", status_code=status.HTTP_201_CREATED)
@audit_operation("create", "risk_methodology")
async def create_methodology(
    payload: MethodologyCreate,
    tenant: Tenant = Depends(get_tenant_record),
    session: AsyncSession = Depends(get_session),
    __: Any = _MethodologiesWriteDep,
):
    item = SafetyRiskMethodology(tenant_id=tenant.id, **payload.model_dump())
    session.add(item)
    await session.commit()
    await session.refresh(item)
    return item


@router.post("/methodologies/{item_id}/clone", status_code=status.HTTP_201_CREATED)
@audit_operation("clone", "risk_methodology")
async def clone_methodology(
    item_id: str,
    payload: MethodologyClone,
    tenant: Tenant = Depends(get_tenant_record),
    session: AsyncSession = Depends(get_session),
    __: Any = _MethodologiesWriteDep,
):
    source = await session.get(SafetyRiskMethodology, item_id)
    if not source or source.tenant_id != tenant.id or source.deleted_at is not None:
        raise HTTPException(404, "Methodology not found")
    clone = SafetyRiskMethodology(
        tenant_id=tenant.id,
        code=source.code,
        name=payload.name or source.name,
        type=source.type,
        status="draft",
        version_no=payload.version_no or (source.version_no + 1),
        formula_json=source.formula_json or {},
        scale_json=source.scale_json or {},
    )
    session.add(clone)
    await session.commit()
    await session.refresh(clone)
    return clone


@router.post("/methodologies/{item_id}/activate")
@audit_operation("activate", "risk_methodology")
async def activate_methodology(
    item_id: str,
    tenant: Tenant = Depends(get_tenant_record),
    session: AsyncSession = Depends(get_session),
    __: Any = _MethodologiesWriteDep,
):
    item = await session.get(SafetyRiskMethodology, item_id)
    if not item or item.tenant_id != tenant.id or item.deleted_at is not None:
        raise HTTPException(404, "Methodology not found")
    rows = (
        (
            await session.execute(
                select(SafetyRiskMethodology).where(
                    SafetyRiskMethodology.tenant_id == tenant.id,
                    SafetyRiskMethodology.code == item.code,
                    SafetyRiskMethodology.deleted_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    for row in rows:
        row.is_default = row.id == item.id
        row.status = "active" if row.id == item.id else "archived"
    await session.commit()
    return {"status": "active", "id": item.id, "affected_versions": len(rows)}


@router.get("/maps")
async def list_maps(
    tenant: Tenant = Depends(get_tenant_record),
    session: AsyncSession = Depends(get_session),
    __: Any = _MapsReadDep,
):
    rows = (
        (
            await session.execute(
                select(SafetyRiskMap)
                .where(SafetyRiskMap.tenant_id == tenant.id, SafetyRiskMap.deleted_at.is_(None))
                .order_by(SafetyRiskMap.updated_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return {"items": rows, "total": len(rows)}


@router.post("/maps", status_code=status.HTTP_201_CREATED)
@audit_operation("create", "risk_map")
async def create_map(
    payload: RiskMapCreate,
    tenant: Tenant = Depends(get_tenant_record),
    session: AsyncSession = Depends(get_session),
    __: Any = _MapsWriteDep,
):
    item = SafetyRiskMap(tenant_id=tenant.id, status="draft", **payload.model_dump())
    session.add(item)
    await session.commit()
    await session.refresh(item)
    return item


@router.post("/maps/{map_id}/items", status_code=status.HTTP_201_CREATED)
@audit_operation("upsert_item", "risk_map")
async def upsert_map_item(
    map_id: str,
    payload: MapItemUpsert,
    tenant: Tenant = Depends(get_tenant_record),
    session: AsyncSession = Depends(get_session),
    __: Any = _MapsWriteDep,
):
    risk_map = await session.get(SafetyRiskMap, map_id)
    if not risk_map or risk_map.tenant_id != tenant.id:
        raise HTTPException(404, "Risk map not found")
    methodology = await session.get(SafetyRiskMethodology, risk_map.risk_methodology_id)
    if methodology is None:
        raise HTTPException(404, "Methodology not found")
    item = (
        await session.execute(
            select(RiskMapItem).where(
                RiskMapItem.tenant_id == tenant.id,
                RiskMapItem.risk_map_id == map_id,
                RiskMapItem.hazard_id == payload.hazard_id,
                RiskMapItem.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    calc = RiskCalculationService.calculate_item(
        {
            "type": (
                methodology.type.value if hasattr(methodology.type, "value") else methodology.type
            ),
            "formula_json": methodology.formula_json,
            "scale_json": methodology.scale_json,
        },
        probability=payload.probability_value,
        severity=payload.severity_value,
        exposure=payload.exposure_value,
    )
    if item is None:
        item = RiskMapItem(tenant_id=tenant.id, risk_map_id=map_id, hazard_id=payload.hazard_id)
        session.add(item)
    item.probability_value = payload.probability_value
    item.severity_value = payload.severity_value
    item.exposure_value = payload.exposure_value
    item.raw_score = calc.raw_score
    item.risk_level = calc.risk_level
    await session.flush()
    for measure_id in payload.measure_ids:
        exists = (
            await session.execute(
                select(RiskMapItemMeasure).where(
                    RiskMapItemMeasure.tenant_id == tenant.id,
                    RiskMapItemMeasure.risk_map_item_id == item.id,
                    RiskMapItemMeasure.measure_id == measure_id,
                )
            )
        ).scalar_one_or_none()
        if exists is None:
            session.add(
                RiskMapItemMeasure(
                    id=str(uuid4()),
                    tenant_id=tenant.id,
                    risk_map_item_id=item.id,
                    measure_id=measure_id,
                    due_date=date.today(),
                    created_at=datetime.now(tz=timezone.utc),
                    updated_at=datetime.now(tz=timezone.utc),
                )
            )
    await session.commit()
    await session.refresh(item)
    return item


@router.post("/maps/{map_id}/recalculate")
@audit_operation("recalculate", "risk_map")
async def recalculate_map(
    map_id: str,
    tenant: Tenant = Depends(get_tenant_record),
    session: AsyncSession = Depends(get_session),
    __: Any = _MapsWriteDep,
):
    risk_map = await session.get(SafetyRiskMap, map_id)
    if not risk_map or risk_map.tenant_id != tenant.id:
        raise HTTPException(404, "Risk map not found")
    methodology = await session.get(SafetyRiskMethodology, risk_map.risk_methodology_id)
    items = (
        (
            await session.execute(
                select(RiskMapItem).where(
                    RiskMapItem.tenant_id == tenant.id,
                    RiskMapItem.risk_map_id == map_id,
                    RiskMapItem.deleted_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    for item in items:
        measure_links = (
            await session.execute(
                select(RiskMapItemMeasure, RiskMeasure)
                .join(RiskMeasure, RiskMeasure.id == RiskMapItemMeasure.measure_id)
                .where(
                    RiskMapItemMeasure.tenant_id == tenant.id,
                    RiskMapItemMeasure.risk_map_item_id == item.id,
                )
            )
        ).all()
        effects = [float(measure.effectiveness_score or 0) for _, measure in measure_links]
        calc = RiskCalculationService.calculate_item(
            {
                "type": (
                    methodology.type.value
                    if hasattr(methodology.type, "value")
                    else methodology.type
                ),
                "formula_json": methodology.formula_json,
                "scale_json": methodology.scale_json,
            },
            probability=float(item.probability_value or 0),
            severity=float(item.severity_value or 0),
            exposure=float(item.exposure_value) if item.exposure_value is not None else None,
        )
        item.raw_score = calc.raw_score
        item.risk_level = calc.risk_level
        residual = (
            RiskMeasureService.residual_from_measures(calc.raw_score, effects)
            if effects
            else calc.raw_score
        )
        item.residual_score = residual
        item.residual_risk_level = RiskCalculationService._pick_level(
            residual,
            RiskCalculationService._normalize_rules(
                (methodology.formula_json or {}).get("ranges", [])
                or (methodology.scale_json or {}).get("level_rules", [])
            ),
        )
    risk_map.calculated_at = datetime.now(tz=timezone.utc)
    risk_map.status = "active"
    await session.commit()
    return {"status": "recalculated", "items": len(items)}


@router.get("/maps/{map_id}/summary")
async def risk_summary(
    map_id: str,
    tenant: Tenant = Depends(get_tenant_record),
    session: AsyncSession = Depends(get_session),
    __: Any = _MapsReadDep,
):
    risk_map = await session.get(SafetyRiskMap, map_id)
    if not risk_map or risk_map.tenant_id != tenant.id:
        raise HTTPException(404, "Risk map not found")
    overdue_measures = int(
        (
            await session.execute(
                select(func.count())
                .select_from(RiskMapItemMeasure)
                .where(
                    RiskMapItemMeasure.tenant_id == tenant.id,
                    RiskMapItemMeasure.due_date.is_not(None),
                    RiskMapItemMeasure.due_date < date.today(),
                    RiskMapItemMeasure.status != "done",
                )
            )
        ).scalar_one()
    )
    open_incidents = int(
        (
            await session.execute(
                select(func.count())
                .select_from(IncidentCase)
                .where(IncidentCase.tenant_id == tenant.id, IncidentCase.status != "closed")
            )
        ).scalar_one()
    )
    open_actions = int(
        (
            await session.execute(
                select(func.count())
                .select_from(CorrectiveAction)
                .where(
                    CorrectiveAction.tenant_id == tenant.id,
                    CorrectiveAction.deleted_at.is_(None),
                    CorrectiveAction.status != "done",
                )
            )
        ).scalar_one()
    )
    item_stats = (
        await session.execute(
            select(
                func.count(), func.avg(RiskMapItem.raw_score), func.avg(RiskMapItem.residual_score)
            ).where(
                RiskMapItem.tenant_id == tenant.id,
                RiskMapItem.risk_map_id == map_id,
                RiskMapItem.deleted_at.is_(None),
            )
        )
    ).one()
    zone_rows = (
        await session.execute(
            select(RiskMapItem.residual_risk_level, func.count())
            .where(
                RiskMapItem.tenant_id == tenant.id,
                RiskMapItem.risk_map_id == map_id,
                RiskMapItem.deleted_at.is_(None),
            )
            .group_by(RiskMapItem.residual_risk_level)
        )
    ).all()
    return {
        "map_id": map_id,
        "items_total": int(item_stats[0] or 0),
        "average_before_score": float(item_stats[1] or 0),
        "average_after_score": float(item_stats[2] or 0),
        "overdue_measures": overdue_measures,
        "incident_pressure": open_incidents,
        "corrective_actions_open": open_actions,
        "risk_zones": {
            str(level.value if hasattr(level, "value") else level or "unrated"): int(count)
            for level, count in zone_rows
        },
    }
