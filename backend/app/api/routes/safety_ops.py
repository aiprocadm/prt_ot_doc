from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.models.models import Tenant
from app.models.safety_ops import (
    CorrectiveAction,
    Finding,
    InspectionPrepGap,
    InspectionPrepItem,
    InspectionPrepPackage,
    OpsPrescription,
)
from app.modules.capa.service import CorrectiveActionService
from app.modules.inspection_prep.service import GapAnalysisService, InspectionPrepPackageService

router = APIRouter(tags=["safety-ops"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[Tenant, Depends(get_tenant_record)]


class FindingIn(BaseModel):
    source_type: str
    source_id: str
    title: str
    severity: str = "medium"
    finding_type: str = "nonconformity"


class FindingUpdate(BaseModel):
    status: str | None = None
    due_date: date | None = None


@router.get("/findings")
async def list_findings(
    tenant: TenantDep,
    session: SessionDep,
    status_filter: str | None = Query(default=None, alias="status"),
) -> list[dict[str, Any]]:
    stmt = select(Finding).where(Finding.tenant_id == str(tenant.id), Finding.deleted_at.is_(None))
    if status_filter:
        stmt = stmt.where(Finding.status == status_filter)
    rows = (await session.execute(stmt.order_by(Finding.created_at.desc()))).scalars().all()
    return [{"id": r.id, "title": r.title, "status": r.status, "severity": r.severity} for r in rows]


@router.post("/findings", status_code=status.HTTP_201_CREATED)
async def create_finding(payload: FindingIn, tenant: TenantDep, session: SessionDep) -> dict[str, str]:
    rec = Finding(tenant_id=str(tenant.id), **payload.model_dump(), status="open")
    session.add(rec)
    await session.commit()
    return {"id": rec.id}


async def _get_finding(session: AsyncSession, tenant_id: str, finding_id: str) -> Finding:
    row = (
        await session.execute(
            select(Finding).where(Finding.id == finding_id, Finding.tenant_id == tenant_id, Finding.deleted_at.is_(None))
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "finding not found")
    return row


@router.patch("/findings/{finding_id}")
async def patch_finding(finding_id: str, payload: FindingUpdate, tenant: TenantDep, session: SessionDep) -> dict[str, str]:
    row = await _get_finding(session, str(tenant.id), finding_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    await session.commit()
    return {"id": row.id}


@router.post("/findings/{finding_id}/resolve")
async def resolve_finding(finding_id: str, tenant: TenantDep, session: SessionDep) -> dict[str, str]:
    row = await _get_finding(session, str(tenant.id), finding_id)
    row.status = "resolved"
    await session.commit()
    return {"status": row.status}


@router.post("/findings/{finding_id}/verify")
async def verify_finding(finding_id: str, tenant: TenantDep, session: SessionDep) -> dict[str, str]:
    row = await _get_finding(session, str(tenant.id), finding_id)
    row.status = "verified"
    await session.commit()
    return {"status": row.status}


class PrescriptionIn(BaseModel):
    code: str
    source_type: str
    title: str


@router.get("/prescriptions")
async def list_prescriptions(tenant: TenantDep, session: SessionDep) -> list[dict[str, str]]:
    rows = (
        await session.execute(
            select(OpsPrescription).where(OpsPrescription.tenant_id == str(tenant.id), OpsPrescription.deleted_at.is_(None))
        )
    ).scalars().all()
    return [{"id": r.id, "code": r.code, "status": r.status} for r in rows]


@router.post("/prescriptions", status_code=status.HTTP_201_CREATED)
async def create_prescription(payload: PrescriptionIn, tenant: TenantDep, session: SessionDep) -> dict[str, str]:
    rec = OpsPrescription(
        tenant_id=str(tenant.id), code=payload.code, source_type=payload.source_type, title=payload.title, status="draft"
    )
    session.add(rec)
    await session.commit()
    return {"id": rec.id}


class CorrectiveActionIn(BaseModel):
    source_type: str
    source_id: str
    title: str
    action_type: str = "corrective"
    due_date: date | None = None


class CorrectiveActionVerifyIn(BaseModel):
    effective: bool
    partial: bool = False
    comment: str | None = None


@router.get("/corrective-actions")
async def list_actions(tenant: TenantDep, session: SessionDep) -> list[dict[str, str]]:
    rows = (
        await session.execute(
            select(CorrectiveAction).where(CorrectiveAction.tenant_id == str(tenant.id), CorrectiveAction.deleted_at.is_(None))
        )
    ).scalars().all()
    return [
        {"id": r.id, "title": r.title, "status": CorrectiveActionService.mark_overdue_if_needed(due_date=r.due_date, status=r.status)}
        for r in rows
    ]


@router.post("/corrective-actions", status_code=status.HTTP_201_CREATED)
async def create_action(payload: CorrectiveActionIn, tenant: TenantDep, session: SessionDep) -> dict[str, str]:
    rec = CorrectiveAction(tenant_id=str(tenant.id), status="open", **payload.model_dump())
    session.add(rec)
    await session.commit()
    return {"id": rec.id}


async def _get_action(session: AsyncSession, tenant_id: str, action_id: str) -> CorrectiveAction:
    row = (
        await session.execute(
            select(CorrectiveAction).where(
                CorrectiveAction.id == action_id,
                CorrectiveAction.tenant_id == tenant_id,
                CorrectiveAction.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "corrective action not found")
    return row


@router.post("/corrective-actions/{action_id}/complete")
async def complete_action(action_id: str, tenant: TenantDep, session: SessionDep) -> dict[str, str]:
    row = await _get_action(session, str(tenant.id), action_id)
    row.status = "done"
    row.completed_at = datetime.now(timezone.utc)
    await session.commit()
    return {"status": row.status}


@router.post("/corrective-actions/{action_id}/verify")
async def verify_action(action_id: str, payload: CorrectiveActionVerifyIn, tenant: TenantDep, session: SessionDep) -> dict[str, str]:
    row = await _get_action(session, str(tenant.id), action_id)
    out = CorrectiveActionService.apply_verification(
        is_effective=payload.effective,
        partially_effective=payload.partial,
        comment=payload.comment,
    )
    row.status = out.status
    row.effectiveness_status = out.effectiveness_status
    row.verification_comment = out.verification_comment
    await session.commit()
    return {"status": row.status, "effectiveness_status": str(row.effectiveness_status)}


class PrepPackageIn(BaseModel):
    code: str
    title: str
    target_inspection_date: date | None = None


@router.get("/inspection-prep/packages")
async def list_prep_packages(tenant: TenantDep, session: SessionDep) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            select(InspectionPrepPackage).where(
                InspectionPrepPackage.tenant_id == str(tenant.id), InspectionPrepPackage.deleted_at.is_(None)
            )
        )
    ).scalars().all()
    return [{"id": p.id, "code": p.code, "title": p.title, "status": p.status} for p in rows]


@router.post("/inspection-prep/packages", status_code=status.HTTP_201_CREATED)
async def create_prep_package(payload: PrepPackageIn, tenant: TenantDep, session: SessionDep) -> dict[str, str]:
    rec = InspectionPrepPackage(
        tenant_id=str(tenant.id),
        code=payload.code,
        title=payload.title,
        status="draft",
        target_inspection_date=payload.target_inspection_date,
    )
    session.add(rec)
    await session.commit()
    return {"id": rec.id}


async def _get_package(session: AsyncSession, tenant_id: str, package_id: str) -> InspectionPrepPackage:
    pack = (
        await session.execute(
            select(InspectionPrepPackage).where(
                InspectionPrepPackage.id == package_id,
                InspectionPrepPackage.tenant_id == tenant_id,
                InspectionPrepPackage.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if pack is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "package not found")
    return pack


@router.get("/inspection-prep/packages/{package_id}/summary")
async def package_summary(package_id: str, tenant: TenantDep, session: SessionDep) -> dict[str, int | str]:
    pack = await _get_package(session, str(tenant.id), package_id)
    items = (
        await session.execute(
            select(InspectionPrepItem).where(InspectionPrepItem.package_id == pack.id, InspectionPrepItem.tenant_id == str(tenant.id))
        )
    ).scalars().all()
    gaps = (
        await session.execute(
            select(InspectionPrepGap).where(InspectionPrepGap.package_id == pack.id, InspectionPrepGap.tenant_id == str(tenant.id))
        )
    ).scalars().all()
    present = sum(1 for item in items if item.status in {"present", "replaced"})
    score = InspectionPrepPackageService.readiness_score(total=len(items), present=present)
    return {"id": pack.id, "status": pack.status, "items": len(items), "gaps": len(gaps), "readiness_score": score}


@router.get("/inspection-prep/packages/{package_id}/items")
async def package_items(package_id: str, tenant: TenantDep, session: SessionDep) -> list[dict[str, str]]:
    pack = await _get_package(session, str(tenant.id), package_id)
    rows = (
        await session.execute(
            select(InspectionPrepItem).where(InspectionPrepItem.package_id == pack.id, InspectionPrepItem.tenant_id == str(tenant.id))
        )
    ).scalars().all()
    return [{"id": row.id, "item_type": row.item_type, "title": row.title, "status": row.status} for row in rows]


@router.get("/inspection-prep/packages/{package_id}/gaps")
async def package_gaps(package_id: str, tenant: TenantDep, session: SessionDep) -> list[dict[str, str]]:
    pack = await _get_package(session, str(tenant.id), package_id)
    rows = (
        await session.execute(
            select(InspectionPrepGap).where(InspectionPrepGap.package_id == pack.id, InspectionPrepGap.tenant_id == str(tenant.id))
        )
    ).scalars().all()
    return [{"id": row.id, "gap_type": row.gap_type, "status": row.status, "severity": row.severity} for row in rows]


@router.post("/inspection-prep/packages/{package_id}/collect")
async def package_collect(package_id: str, tenant: TenantDep, session: SessionDep) -> dict[str, str]:
    pack = await _get_package(session, str(tenant.id), package_id)
    pack.status = "collecting"
    defaults = InspectionPrepPackageService.collect_required_items()
    for item in defaults:
        session.add(
            InspectionPrepItem(
                tenant_id=str(tenant.id),
                package_id=pack.id,
                item_type=item["item_type"],
                title=item["title"],
                status="required",
            )
        )
    await session.commit()
    return {"status": pack.status}


class GapAnalysisIn(BaseModel):
    missing_documents: int = Field(default=0, ge=0)
    open_prescriptions: int = Field(default=0, ge=0)
    overdue_actions: int = Field(default=0, ge=0)
    high_risks: int = Field(default=0, ge=0)


@router.post("/inspection-prep/packages/{package_id}/run-gap-analysis")
async def package_gap_analysis(
    package_id: str,
    tenant: TenantDep,
    session: SessionDep,
    payload: GapAnalysisIn,
) -> dict[str, str]:
    pack = await _get_package(session, str(tenant.id), package_id)
    pack.status = "gap_analysis"
    await session.execute(
        InspectionPrepGap.__table__.delete().where(
            InspectionPrepGap.package_id == pack.id,
            InspectionPrepGap.tenant_id == str(tenant.id),
        )
    )
    for gap in GapAnalysisService.detect_gaps(
        missing_documents=payload.missing_documents,
        open_prescriptions=payload.open_prescriptions,
        overdue_actions=payload.overdue_actions,
        high_risks=payload.high_risks,
    ):
        session.add(
            InspectionPrepGap(
                tenant_id=str(tenant.id),
                package_id=pack.id,
                gap_type=gap.gap_type,
                severity=gap.severity,
                title=gap.title,
                status="open",
            )
        )
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


@router.get("/inspection-prep/packages/{package_id}")
async def get_package(package_id: str, tenant: TenantDep, session: SessionDep) -> dict[str, str | None]:
    pack = await _get_package(session, str(tenant.id), package_id)
    return {"id": pack.id, "code": pack.code, "title": pack.title, "status": pack.status}


@router.delete(
    "/inspection-prep/packages/{package_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def delete_package(package_id: str, tenant: TenantDep, session: SessionDep) -> None:
    pack = await _get_package(session, str(tenant.id), package_id)
    pack.deleted_at = datetime.now(timezone.utc)
    await session.commit()


@router.get("/inspection-prep/packages/{package_id}/stats")
async def package_stats(package_id: str, tenant: TenantDep, session: SessionDep) -> dict[str, int]:
    pack = await _get_package(session, str(tenant.id), package_id)
    items_total = await session.scalar(
        select(func.count()).select_from(InspectionPrepItem).where(
            InspectionPrepItem.package_id == pack.id, InspectionPrepItem.tenant_id == str(tenant.id)
        )
    )
    gaps_total = await session.scalar(
        select(func.count()).select_from(InspectionPrepGap).where(
            InspectionPrepGap.package_id == pack.id, InspectionPrepGap.tenant_id == str(tenant.id)
        )
    )
    return {"items": int(items_total or 0), "gaps": int(gaps_total or 0)}
