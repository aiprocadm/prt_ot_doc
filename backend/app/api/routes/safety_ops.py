from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.models.models import Tenant
from app.models.safety_ops import CorrectiveAction, Finding, InspectionPrepGap, InspectionPrepItem, InspectionPrepPackage, OpsPrescription

router = APIRouter(tags=["safety-ops"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[Tenant, Depends(get_tenant_record)]


class FindingIn(BaseModel):
    source_type: str
    source_id: str
    title: str
    severity: str = "medium"
    finding_type: str = "nonconformity"


@router.get("/findings")
async def list_findings(tenant: TenantDep, session: SessionDep) -> list[FindingIn]:
    rows = (await session.execute(select(Finding).where(Finding.tenant_id == str(tenant.id), Finding.deleted_at.is_(None)))).scalars().all()
    return [FindingIn.model_validate(r, from_attributes=True) for r in rows]


@router.post("/findings", status_code=status.HTTP_201_CREATED)
async def create_finding(payload: FindingIn, tenant: TenantDep, session: SessionDep) -> dict[str, str]:
    rec = Finding(tenant_id=str(tenant.id), **payload.model_dump(), status="open")
    session.add(rec)
    await session.commit()
    return {"id": rec.id}


class PrescriptionIn(BaseModel):
    code: str
    source_type: str
    title: str


@router.get("/prescriptions")
async def list_prescriptions(tenant: TenantDep, session: SessionDep) -> list[dict[str, str]]:
    rows = (await session.execute(select(OpsPrescription).where(OpsPrescription.tenant_id == str(tenant.id), OpsPrescription.deleted_at.is_(None)))).scalars().all()
    return [{"id": r.id, "code": r.code, "status": r.status} for r in rows]


@router.post("/prescriptions", status_code=status.HTTP_201_CREATED)
async def create_prescription(payload: PrescriptionIn, tenant: TenantDep, session: SessionDep) -> dict[str, str]:
    rec = OpsPrescription(tenant_id=str(tenant.id), code=payload.code, source_type=payload.source_type, title=payload.title, status="draft")
    session.add(rec)
    await session.commit()
    return {"id": rec.id}


class CorrectiveActionIn(BaseModel):
    source_type: str
    source_id: str
    title: str
    action_type: str = "corrective"


@router.get("/corrective-actions")
async def list_actions(tenant: TenantDep, session: SessionDep) -> list[dict[str, str]]:
    rows = (await session.execute(select(CorrectiveAction).where(CorrectiveAction.tenant_id == str(tenant.id), CorrectiveAction.deleted_at.is_(None)))).scalars().all()
    return [{"id": r.id, "title": r.title, "status": r.status} for r in rows]


@router.post("/corrective-actions", status_code=status.HTTP_201_CREATED)
async def create_action(payload: CorrectiveActionIn, tenant: TenantDep, session: SessionDep) -> dict[str, str]:
    rec = CorrectiveAction(tenant_id=str(tenant.id), status="open", **payload.model_dump())
    session.add(rec)
    await session.commit()
    return {"id": rec.id}


class PrepPackageIn(BaseModel):
    code: str
    title: str


@router.post("/inspection-prep/packages", status_code=status.HTTP_201_CREATED)
async def create_prep_package(payload: PrepPackageIn, tenant: TenantDep, session: SessionDep) -> dict[str, str]:
    rec = InspectionPrepPackage(tenant_id=str(tenant.id), code=payload.code, title=payload.title, status="draft")
    session.add(rec)
    await session.commit()
    return {"id": rec.id}


async def _get_package(session: AsyncSession, tenant_id: str, package_id: str) -> InspectionPrepPackage:
    pack = (await session.execute(select(InspectionPrepPackage).where(InspectionPrepPackage.id == package_id, InspectionPrepPackage.tenant_id == tenant_id, InspectionPrepPackage.deleted_at.is_(None)))).scalar_one_or_none()
    if pack is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "package not found")
    return pack


@router.get("/inspection-prep/packages/{package_id}/summary")
async def package_summary(package_id: str, tenant: TenantDep, session: SessionDep) -> dict[str, int | str]:
    pack = await _get_package(session, str(tenant.id), package_id)
    items = (await session.execute(select(InspectionPrepItem).where(InspectionPrepItem.package_id == pack.id, InspectionPrepItem.tenant_id == str(tenant.id)))).scalars().all()
    gaps = (await session.execute(select(InspectionPrepGap).where(InspectionPrepGap.package_id == pack.id, InspectionPrepGap.tenant_id == str(tenant.id)))).scalars().all()
    return {"id": pack.id, "status": pack.status, "items": len(items), "gaps": len(gaps)}


@router.get("/inspection-prep/packages/{package_id}/gaps")
async def package_gaps(package_id: str, tenant: TenantDep, session: SessionDep) -> list[dict[str, str]]:
    pack = await _get_package(session, str(tenant.id), package_id)
    rows = (await session.execute(select(InspectionPrepGap).where(InspectionPrepGap.package_id == pack.id, InspectionPrepGap.tenant_id == str(tenant.id)))).scalars().all()
    return [{"id": row.id, "gap_type": row.gap_type, "status": row.status} for row in rows]


@router.post("/inspection-prep/packages/{package_id}/collect")
async def package_collect(package_id: str, tenant: TenantDep, session: SessionDep) -> dict[str, str]:
    pack = await _get_package(session, str(tenant.id), package_id)
    pack.status = "collecting"
    session.add(InspectionPrepItem(tenant_id=str(tenant.id), package_id=pack.id, item_type="risk_map", title="Risk map", status="present"))
    await session.commit()
    return {"status": pack.status}


@router.post("/inspection-prep/packages/{package_id}/run-gap-analysis")
async def package_gap_analysis(package_id: str, tenant: TenantDep, session: SessionDep) -> dict[str, str]:
    pack = await _get_package(session, str(tenant.id), package_id)
    pack.status = "gap_analysis"
    session.add(InspectionPrepGap(tenant_id=str(tenant.id), package_id=pack.id, gap_type="open_prescription", severity="medium", title="Open prescriptions", status="open"))
    await session.commit()
    return {"status": pack.status}


@router.post("/inspection-prep/packages/{package_id}/export")
async def package_export(package_id: str, tenant: TenantDep, session: SessionDep) -> dict[str, str]:
    pack = await _get_package(session, str(tenant.id), package_id)
    pack.status = "exported"
    await session.commit()
    return {"status": pack.status}


@router.post("/inspection-prep/packages/{package_id}/send-edo")
async def package_send_edo(package_id: str, tenant: TenantDep, session: SessionDep) -> dict[str, str]:
    pack = await _get_package(session, str(tenant.id), package_id)
    pack.status = "sent_to_edo"
    pack.updated_at = datetime.now(timezone.utc)
    await session.commit()
    return {"status": pack.status}
