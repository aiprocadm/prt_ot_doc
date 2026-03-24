from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_correlation_id, get_session, get_tenant_record
from app.core.security import AccessContext, abac
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
from app.services.audit import AuditService
from app.core.permission_checker import PermissionChecker
from app.core.tenant_validation import TenantContextValidator

router = APIRouter(tags=["safety-ops"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[Tenant, Depends(get_tenant_record)]

_MANAGER_ROLES = ["admin", "owner", "line_manager", "hr"]
_EDITOR_ROLES = ["admin", "owner", "line_manager"]


def _tenant_resource_id(tenant: Tenant = Depends(get_tenant_record)) -> str | None:
    return getattr(tenant, "id", None)


ManagerAccess = Annotated[
    AccessContext,
    Depends(abac(_tenant_resource_id, required_roles=_MANAGER_ROLES, action="read safety ops")),
]
EditorAccess = Annotated[
    AccessContext,
    Depends(abac(_tenant_resource_id, required_roles=_EDITOR_ROLES, action="manage safety ops")),
]


class FindingIn(BaseModel):
    source_type: str
    source_id: str
    title: str
    severity: str = "medium"
    finding_type: str = "nonconformity"
    description: str | None = None
    due_date: date | None = None
    site_id: str | None = None


class FindingUpdate(BaseModel):
    status: str | None = None
    due_date: date | None = None
    description: str | None = None
    severity: str | None = None


class PrescriptionIn(BaseModel):
    code: str
    source_type: str
    title: str


class CorrectiveActionIn(BaseModel):
    source_type: str
    source_id: str
    title: str
    action_type: str = "corrective"
    due_date: date | None = None
    description: str | None = None
    responsible_user_id: str | None = None
    site_id: str | None = None


class CorrectiveActionVerifyIn(BaseModel):
    effective: bool
    partial: bool = False
    comment: str | None = None


class PrepPackageIn(BaseModel):
    code: str
    title: str
    target_inspection_date: date | None = None


class FindingProjection(BaseModel):
    id: str
    title: str
    status: str
    severity: str
    source_type: str
    source_id: str
    finding_type: str
    due_date: date | None = None
    site_id: str | None = None
    description: str | None = None
    created_at: datetime | None = None


class CorrectiveActionProjection(BaseModel):
    id: str
    title: str
    status: str
    source_type: str
    source_id: str
    action_type: str
    due_date: date | None = None
    responsible_user_id: str | None = None
    site_id: str | None = None
    effectiveness_status: str | None = None
    description: str | None = None
    completed_at: datetime | None = None



def _serialize_finding(row: Finding) -> dict[str, Any]:
    return FindingProjection(
        id=row.id,
        title=row.title,
        status=row.status,
        severity=row.severity,
        source_type=row.source_type,
        source_id=row.source_id,
        finding_type=row.finding_type,
        due_date=row.due_date,
        site_id=row.site_id,
        description=row.description,
        created_at=row.created_at,
    ).model_dump(mode="json")



def _serialize_action(row: CorrectiveAction) -> dict[str, Any]:
    return CorrectiveActionProjection(
        id=row.id,
        title=row.title,
        status=CorrectiveActionService.mark_overdue_if_needed(due_date=row.due_date, status=row.status),
        source_type=row.source_type,
        source_id=row.source_id,
        action_type=row.action_type,
        due_date=row.due_date,
        responsible_user_id=row.responsible_user_id,
        site_id=row.site_id,
        effectiveness_status=row.effectiveness_status,
        description=row.description,
        completed_at=row.completed_at,
    ).model_dump(mode="json")


async def _audit_event(
    request: Request,
    session: AsyncSession,
    *,
    tenant_id: str,
    action: str,
    object_type: str,
    object_id: str,
    user_id: str | None,
    details: dict[str, Any],
) -> None:
    await AuditService(session).log_event(
        tenant_id=tenant_id,
        action=action,
        object_type=object_type,
        object_id=object_id,
        user_id=user_id,
        ip=request.client.host if request.client else "unknown",
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
        details=details,
    )


@router.get("/findings")
async def list_findings(
    tenant: TenantDep,
    session: SessionDep,
    _: ManagerAccess,
    status_filter: str | None = Query(default=None, alias="status"),
    severity: str | None = Query(default=None),
    source_type: str | None = Query(default=None),
) -> list[dict[str, Any]]:
    stmt = select(Finding).where(Finding.tenant_id == str(tenant.id), Finding.deleted_at.is_(None))
    if status_filter:
        stmt = stmt.where(Finding.status == status_filter)
    if severity:
        stmt = stmt.where(Finding.severity == severity)
    if source_type:
        stmt = stmt.where(Finding.source_type == source_type)
    rows = (await session.execute(stmt.order_by(Finding.created_at.desc()))).scalars().all()
    return [_serialize_finding(r) for r in rows]


@router.post("/findings", status_code=status.HTTP_201_CREATED)
async def create_finding(
    payload: FindingIn,
    request: Request,
    tenant: TenantDep,
    session: SessionDep,
    access: EditorAccess,
) -> dict[str, str]:
    rec = Finding(
        tenant_id=str(tenant.id),
        source_type=payload.source_type,
        source_id=payload.source_id,
        title=payload.title,
        severity=payload.severity,
        finding_type=payload.finding_type,
        description=payload.description,
        due_date=payload.due_date,
        site_id=payload.site_id,
        created_by=getattr(access.user, "id", None),
        status="open",
    )
    session.add(rec)
    await session.flush()
    await _audit_event(
        request,
        session,
        tenant_id=str(tenant.id),
        action="create",
        object_type="finding",
        object_id=rec.id,
        user_id=getattr(access.user, "id", None),
        details={"source_type": rec.source_type, "severity": rec.severity},
    )
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
async def patch_finding(
    finding_id: str,
    payload: FindingUpdate,
    request: Request,
    tenant: TenantDep,
    session: SessionDep,
    access: EditorAccess,
) -> dict[str, Any]:
    row = await _get_finding(session, str(tenant.id), finding_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    await _audit_event(
        request,
        session,
        tenant_id=str(tenant.id),
        action="update",
        object_type="finding",
        object_id=row.id,
        user_id=getattr(access.user, "id", None),
        details={"status": row.status, "severity": row.severity},
    )
    await session.commit()
    return _serialize_finding(row)


@router.post("/findings/{finding_id}/resolve")
async def resolve_finding(
    finding_id: str,
    request: Request,
    tenant: TenantDep,
    session: SessionDep,
    access: EditorAccess,
) -> dict[str, Any]:
    row = await _get_finding(session, str(tenant.id), finding_id)
    row.status = "resolved"
    await _audit_event(
        request,
        session,
        tenant_id=str(tenant.id),
        action="resolve",
        object_type="finding",
        object_id=row.id,
        user_id=getattr(access.user, "id", None),
        details={"status": row.status},
    )
    await session.commit()
    return _serialize_finding(row)


@router.post("/findings/{finding_id}/verify")
async def verify_finding(
    finding_id: str,
    request: Request,
    tenant: TenantDep,
    session: SessionDep,
    access: EditorAccess,
) -> dict[str, Any]:
    row = await _get_finding(session, str(tenant.id), finding_id)
    row.status = "verified"
    await _audit_event(
        request,
        session,
        tenant_id=str(tenant.id),
        action="verify",
        object_type="finding",
        object_id=row.id,
        user_id=getattr(access.user, "id", None),
        details={"status": row.status},
    )
    await session.commit()
    return _serialize_finding(row)


@router.get("/prescriptions")
async def list_prescriptions(tenant: TenantDep, session: SessionDep, _: ManagerAccess) -> list[dict[str, str]]:
    rows = (
        await session.execute(
            select(OpsPrescription).where(OpsPrescription.tenant_id == str(tenant.id), OpsPrescription.deleted_at.is_(None))
        )
    ).scalars().all()
    return [{"id": r.id, "code": r.code, "status": r.status} for r in rows]


@router.post("/prescriptions", status_code=status.HTTP_201_CREATED)
async def create_prescription(
    payload: PrescriptionIn,
    request: Request,
    tenant: TenantDep,
    session: SessionDep,
    access: EditorAccess,
) -> dict[str, str]:
    rec = OpsPrescription(
        tenant_id=str(tenant.id), code=payload.code, source_type=payload.source_type, title=payload.title, status="draft"
    )
    session.add(rec)
    await session.flush()
    await _audit_event(
        request,
        session,
        tenant_id=str(tenant.id),
        action="create",
        object_type="ops_prescription",
        object_id=rec.id,
        user_id=getattr(access.user, "id", None),
        details={"code": rec.code, "source_type": rec.source_type},
    )
    await session.commit()
    return {"id": rec.id}


@router.get("/corrective-actions")
async def list_actions(
    tenant: TenantDep,
    session: SessionDep,
    _: ManagerAccess,
    status_filter: str | None = Query(default=None, alias="status"),
    source_type: str | None = Query(default=None),
) -> list[dict[str, Any]]:
    stmt = select(CorrectiveAction).where(CorrectiveAction.tenant_id == str(tenant.id), CorrectiveAction.deleted_at.is_(None))
    if status_filter:
        stmt = stmt.where(CorrectiveAction.status == status_filter)
    if source_type:
        stmt = stmt.where(CorrectiveAction.source_type == source_type)
    rows = (await session.execute(stmt.order_by(CorrectiveAction.due_date.asc().nullslast(), CorrectiveAction.created_at.desc()))).scalars().all()
    return [_serialize_action(r) for r in rows]


@router.post("/corrective-actions", status_code=status.HTTP_201_CREATED)
async def create_action(
    payload: CorrectiveActionIn,
    request: Request,
    tenant: TenantDep,
    session: SessionDep,
    access: EditorAccess,
) -> dict[str, str]:
    rec = CorrectiveAction(
        tenant_id=str(tenant.id),
        status="open",
        source_type=payload.source_type,
        source_id=payload.source_id,
        title=payload.title,
        action_type=payload.action_type,
        due_date=payload.due_date,
        description=payload.description,
        responsible_user_id=payload.responsible_user_id,
        site_id=payload.site_id,
    )
    session.add(rec)
    await session.flush()
    await _audit_event(
        request,
        session,
        tenant_id=str(tenant.id),
        action="create",
        object_type="corrective_action",
        object_id=rec.id,
        user_id=getattr(access.user, "id", None),
        details={"source_type": rec.source_type, "action_type": rec.action_type},
    )
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
async def complete_action(
    action_id: str,
    request: Request,
    tenant: TenantDep,
    session: SessionDep,
    access: EditorAccess,
) -> dict[str, Any]:
    row = await _get_action(session, str(tenant.id), action_id)
    row.status = "done"
    row.completed_at = datetime.now(timezone.utc)
    await _audit_event(
        request,
        session,
        tenant_id=str(tenant.id),
        action="complete",
        object_type="corrective_action",
        object_id=row.id,
        user_id=getattr(access.user, "id", None),
        details={"status": row.status},
    )
    await session.commit()
    return _serialize_action(row)


@router.post("/corrective-actions/{action_id}/verify")
async def verify_action(
    action_id: str,
    payload: CorrectiveActionVerifyIn,
    request: Request,
    tenant: TenantDep,
    session: SessionDep,
    access: EditorAccess,
) -> dict[str, Any]:
    row = await _get_action(session, str(tenant.id), action_id)
    out = CorrectiveActionService.apply_verification(
        is_effective=payload.effective,
        partially_effective=payload.partial,
        comment=payload.comment,
    )
    row.status = out.status
    row.effectiveness_status = out.effectiveness_status
    row.verification_comment = out.verification_comment
    await _audit_event(
        request,
        session,
        tenant_id=str(tenant.id),
        action="verify",
        object_type="corrective_action",
        object_id=row.id,
        user_id=getattr(access.user, "id", None),
        details={"status": row.status, "effectiveness_status": row.effectiveness_status},
    )
    await session.commit()
    return _serialize_action(row)


@router.get("/inspection-prep/packages")
async def list_prep_packages(tenant: TenantDep, session: SessionDep, _: ManagerAccess) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            select(InspectionPrepPackage).where(
                InspectionPrepPackage.tenant_id == str(tenant.id), InspectionPrepPackage.deleted_at.is_(None)
            )
        )
    ).scalars().all()
    return [{"id": p.id, "code": p.code, "title": p.title, "status": p.status} for p in rows]


@router.post("/inspection-prep/packages", status_code=status.HTTP_201_CREATED)
async def create_prep_package(
    payload: PrepPackageIn,
    request: Request,
    tenant: TenantDep,
    session: SessionDep,
    access: EditorAccess,
) -> dict[str, str]:
    rec = InspectionPrepPackage(
        tenant_id=str(tenant.id),
        code=payload.code,
        title=payload.title,
        status="draft",
        target_inspection_date=payload.target_inspection_date,
    )
    session.add(rec)
    await session.flush()
    await _audit_event(
        request,
        session,
        tenant_id=str(tenant.id),
        action="create",
        object_type="inspection_prep_package",
        object_id=rec.id,
        user_id=getattr(access.user, "id", None),
        details={"code": rec.code},
    )
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
async def package_summary(package_id: str, tenant: TenantDep, session: SessionDep, _: ManagerAccess) -> dict[str, int | str]:
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
async def package_items(package_id: str, tenant: TenantDep, session: SessionDep, _: ManagerAccess) -> list[dict[str, str]]:
    pack = await _get_package(session, str(tenant.id), package_id)
    rows = (
        await session.execute(
            select(InspectionPrepItem).where(InspectionPrepItem.package_id == pack.id, InspectionPrepItem.tenant_id == str(tenant.id))
        )
    ).scalars().all()
    return [{"id": row.id, "item_type": row.item_type, "title": row.title, "status": row.status} for row in rows]


@router.get("/inspection-prep/packages/{package_id}/gaps")
async def package_gaps(package_id: str, tenant: TenantDep, session: SessionDep, _: ManagerAccess) -> list[dict[str, str]]:
    pack = await _get_package(session, str(tenant.id), package_id)
    rows = (
        await session.execute(
            select(InspectionPrepGap).where(InspectionPrepGap.package_id == pack.id, InspectionPrepGap.tenant_id == str(tenant.id))
        )
    ).scalars().all()
    return [{"id": row.id, "gap_type": row.gap_type, "severity": row.severity, "title": row.title} for row in rows]


class GapRecalcIn(BaseModel):
    missing_documents: int = Field(0, ge=0)
    open_prescriptions: int = Field(0, ge=0)
    overdue_actions: int = Field(0, ge=0)
    high_risks: int = Field(0, ge=0)


@router.post("/inspection-prep/packages/{package_id}/recalculate-gaps")
async def recalc_gaps(
    package_id: str,
    payload: GapRecalcIn,
    request: Request,
    tenant: TenantDep,
    session: SessionDep,
    access: EditorAccess,
) -> Response:
    pack = await _get_package(session, str(tenant.id), package_id)
    await GapAnalysisService.recalculate_package_gaps(
        session,
        package_id=pack.id,
        tenant_id=str(tenant.id),
        missing_documents=payload.missing_documents,
        open_prescriptions=payload.open_prescriptions,
        overdue_actions=payload.overdue_actions,
        high_risks=payload.high_risks,
    )
    await _audit_event(
        request,
        session,
        tenant_id=str(tenant.id),
        action="recalculate_gaps",
        object_type="inspection_prep_package",
        object_id=pack.id,
        user_id=getattr(access.user, "id", None),
        details=payload.model_dump(),
    )
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/inspection-prep/summary")
async def prep_summary(
    tenant: TenantDep,
    session: SessionDep,
    _: ManagerAccess,
) -> dict[str, int]:
    packages_total = await session.scalar(
        select(func.count()).select_from(
            select(InspectionPrepPackage.id).where(
                InspectionPrepPackage.tenant_id == str(tenant.id), InspectionPrepPackage.deleted_at.is_(None)
            ).subquery()
        )
    )
    gap_total = await session.scalar(
        select(func.count()).select_from(
            select(InspectionPrepGap.id).where(InspectionPrepGap.tenant_id == str(tenant.id)).subquery()
        )
    )
    return {"packages": int(packages_total or 0), "gaps": int(gap_total or 0)}
