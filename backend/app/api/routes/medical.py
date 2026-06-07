"""Medical requirement endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.api.helpers.etag import (
    apply_etag_response_headers,
    build_not_modified_headers,
    compute_list_etag,
)
from app.core.audit_decorator import audit_operation
from app.core.feature_flags import is_feature_enabled
from app.core.security import AccessContext, abac
from app.core.tenant_validation import TenantContextValidator
from app.domains.medical import lifecycle as lc
from app.domains.medical import service as medsvc
from app.models.models import MedicalExam, MedicalSuspension, MedicalSuspensionStatus, Person, Tenant
from app.schemas.medical import (
    MedicalExamCreate, MedicalExamPage, MedicalExamRead, MedicalRequirementCreate,
    MedicalSuspensionPage, MedicalSuspensionRead,
)
from app.schemas.task import TaskRead
from app.services.obligations import create_medical_task

router = APIRouter(tags=["medical"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[Tenant, Depends(get_tenant_record)]



def _tenant_resource_id(tenant: Tenant = Depends(get_tenant_record)) -> UUID | None:
    return getattr(tenant, "id", None)


_MEDICAL_WRITE_ROLES = ["admin", "owner", "hr"]
_MEDICAL_READ_ROLES = ["admin", "owner", "hr", "line_manager"]


MedicalAccess = Annotated[
    AccessContext,
    Depends(abac(_tenant_resource_id, required_roles=_MEDICAL_WRITE_ROLES, action="manage medical")),
]
MedicalReadAccess = Annotated[
    AccessContext,
    Depends(abac(_tenant_resource_id, required_roles=_MEDICAL_READ_ROLES, action="read medical")),
]

_MEDICAL_FEATURE_CODE = "medical"


async def require_medical_feature(tenant: TenantDep, session: SessionDep) -> None:
    if not await is_feature_enabled(session, str(tenant.id), _MEDICAL_FEATURE_CODE):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Medical feature is not enabled for this tenant")


MedicalFeatureGate = Depends(require_medical_feature)


def _error(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


@router.get("/medical/exams", response_model=MedicalExamPage)
async def list_medical_exams(
    request: Request,
    response: Response,
    tenant: TenantDep,
    session: SessionDep,
    access: MedicalReadAccess,
    person_id: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> MedicalExamPage | Response:
    TenantContextValidator.ensure_tenant_context(tenant)

    _ = access
    stmt = select(MedicalExam).where(MedicalExam.tenant_id == tenant.id, MedicalExam.deleted_at.is_(None))
    if person_id:
        stmt = stmt.where(MedicalExam.person_id == person_id)
    if status_filter == "expired":
        stmt = stmt.where(MedicalExam.valid_until < func.current_date())
    elif status_filter == "upcoming":
        stmt = stmt.where(MedicalExam.valid_until >= func.current_date())

    total_stmt = select(func.count()).select_from(stmt.subquery())
    rows = list((
        await session.execute(
            stmt.order_by(MedicalExam.valid_until.asc(), MedicalExam.exam_date.desc()).offset(offset).limit(limit)
        )
    ).scalars().all())
    total = await session.scalar(total_stmt)
    etag = compute_list_etag(
        tenant_id=str(tenant.id),
        items=rows,
        scalars=[
            ("total", int(total or 0)),
            ("limit", limit),
            ("offset", offset),
            ("person", person_id or ""),
            ("status", status_filter or ""),
        ],
    )
    apply_etag_response_headers(response, etag)
    if request.headers.get("if-none-match") == etag:
        return Response(
            status_code=status.HTTP_304_NOT_MODIFIED,
            headers=build_not_modified_headers(etag),
        )
    return MedicalExamPage(items=[MedicalExamRead.model_validate(item) for item in rows], total=int(total or 0))


@router.post("/medical/requirements", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
@audit_operation("create", "medical_requirement")
async def create_medical_requirement(
    payload: MedicalRequirementCreate,
    tenant: TenantDep,
    session: SessionDep,
    access: MedicalAccess,
) -> TaskRead:
    TenantContextValidator.ensure_tenant_context(tenant)

    person = await session.scalar(
        select(Person).where(Person.id == payload.person_id, Person.tenant_id == tenant.id, Person.deleted_at.is_(None))
    )
    if person is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Person not found")
    task = await create_medical_task(
        session,
        tenant_id=str(tenant.id),
        person_id=payload.person_id,
        actor_id=getattr(access.user, "id", None),
        due_date=payload.due_date,
    )
    await session.commit()
    await session.refresh(task)
    return TaskRead.model_validate(task)


@router.post("/medical/exams", response_model=MedicalExamRead,
             status_code=status.HTTP_201_CREATED, dependencies=[MedicalFeatureGate])
async def create_medical_exam(
    payload: MedicalExamCreate, tenant: TenantDep, session: SessionDep, access: MedicalAccess,
) -> MedicalExamRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    try:
        exam = await medsvc.record_exam(
            session, tenant_id=str(tenant.id), actor_id=getattr(access.user, "id", None),
            person_id=payload.person_id, exam_kind=payload.exam_kind,
            exam_date=payload.exam_date, fitness=payload.fitness,
            contraindications=payload.contraindications, conclusion=payload.conclusion,
            restrictions=payload.restrictions, valid_until=payload.valid_until,
            medical_org_name=payload.medical_org_name, referral_id=payload.referral_id,
            exam_type=payload.exam_type,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc))
    await session.commit()
    await session.refresh(exam)
    return MedicalExamRead.model_validate(exam)


@router.get("/medical/suspensions", response_model=MedicalSuspensionPage,
            dependencies=[MedicalFeatureGate])
async def list_suspensions(
    tenant: TenantDep, session: SessionDep, access: MedicalReadAccess,
    person_id: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
) -> MedicalSuspensionPage:
    TenantContextValidator.ensure_tenant_context(tenant)
    _ = access
    stmt = select(MedicalSuspension).where(
        MedicalSuspension.tenant_id == tenant.id, MedicalSuspension.deleted_at.is_(None))
    if person_id:
        stmt = stmt.where(MedicalSuspension.person_id == person_id)
    if status_filter == "active":
        stmt = stmt.where(MedicalSuspension.status == MedicalSuspensionStatus.ACTIVE)
    rows = list((await session.execute(stmt)).scalars().all())
    return MedicalSuspensionPage(
        items=[MedicalSuspensionRead.model_validate(r) for r in rows], total=len(rows))
