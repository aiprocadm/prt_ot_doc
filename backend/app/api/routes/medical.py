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
from app.models.models import (
    MedicalExam,
    MedicalFactor,
    MedicalNorm,
    MedicalReferral,
    MedicalReferralStatus,
    MedicalSuspension,
    MedicalSuspensionStatus,
    Person,
    Tenant,
)
from app.schemas.medical import (
    ContingentItem,
    ContingentPage,
    ContingentRegisterPage,
    ContingentRegisterRow,
    MedicalExamCreate,
    MedicalExamPage,
    MedicalExamRead,
    MedicalExamUpdate,
    MedicalFactorCreate,
    MedicalFactorPage,
    MedicalFactorRead,
    MedicalFactorUpdate,
    MedicalNormCreate,
    MedicalNormPage,
    MedicalNormRead,
    MedicalNormUpdate,
    MedicalReferralCreate,
    MedicalReferralPage,
    MedicalReferralRead,
    MedicalReferralTransition,
    MedicalRequirementCreate,
    MedicalSummary,
    MedicalSuspensionPage,
    MedicalSuspensionRead,
    NamedListPage,
    NamedListRow,
)
from app.schemas.task import TaskRead
from app.services.audit import AuditService
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
    Depends(
        abac(_tenant_resource_id, required_roles=_MEDICAL_WRITE_ROLES, action="manage medical")
    ),
]
MedicalReadAccess = Annotated[
    AccessContext,
    Depends(abac(_tenant_resource_id, required_roles=_MEDICAL_READ_ROLES, action="read medical")),
]

_MEDICAL_FEATURE_CODE = "medical"


async def require_medical_feature(tenant: TenantDep, session: SessionDep) -> None:
    if not await is_feature_enabled(session, str(tenant.id), _MEDICAL_FEATURE_CODE):
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Medical feature is not enabled for this tenant"
        )


MedicalFeatureGate = Depends(require_medical_feature)


def _error(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def _to_referral_read(record: MedicalReferral, *, today) -> MedicalReferralRead:
    return MedicalReferralRead.model_validate(record).model_copy(
        update={"is_overdue": lc.is_overdue(record.due_at, record.status, today)}
    )


async def _get_factor(session: AsyncSession, tenant_id: str, factor_id: str) -> MedicalFactor:
    rec = (
        await session.execute(
            select(MedicalFactor).where(
                MedicalFactor.id == factor_id,
                MedicalFactor.tenant_id == tenant_id,
            )
        )
    ).scalar_one_or_none()
    if rec is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=_error("medical_factor_not_found", "Medical factor not found"),
        )
    return rec


async def _get_norm(session: AsyncSession, tenant_id: str, norm_id: str) -> MedicalNorm:
    from app.models.models import MedicalNorm as _MN

    rec = (
        await session.execute(
            select(_MN).where(
                _MN.id == norm_id,
                _MN.tenant_id == tenant_id,
            )
        )
    ).scalar_one_or_none()
    if rec is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=_error("medical_norm_not_found", "Medical norm not found"),
        )
    return rec


async def _get_referral(session: AsyncSession, tenant_id: str, referral_id: str) -> MedicalReferral:
    rec = (
        await session.execute(
            select(MedicalReferral).where(
                MedicalReferral.id == referral_id,
                MedicalReferral.tenant_id == tenant_id,
                MedicalReferral.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if rec is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=_error("referral_not_found", "Referral not found"),
        )
    return rec


@router.get("/medical/exams", response_model=MedicalExamPage)
async def list_medical_exams(
    request: Request,
    response: Response,
    tenant: TenantDep,
    session: SessionDep,
    access: MedicalReadAccess,
    person_id: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    exam_kind: str | None = Query(default=None),
    fitness: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> MedicalExamPage | Response:
    TenantContextValidator.ensure_tenant_context(tenant)

    _ = access
    stmt = select(MedicalExam).where(
        MedicalExam.tenant_id == tenant.id, MedicalExam.deleted_at.is_(None)
    )
    if person_id:
        stmt = stmt.where(MedicalExam.person_id == person_id)
    if status_filter == "expired":
        stmt = stmt.where(MedicalExam.valid_until < func.current_date())
    elif status_filter == "upcoming":
        stmt = stmt.where(MedicalExam.valid_until >= func.current_date())
    if exam_kind:
        stmt = stmt.where(MedicalExam.exam_kind == exam_kind)
    if fitness:
        stmt = stmt.where(MedicalExam.fitness == fitness)

    total_stmt = select(func.count()).select_from(stmt.subquery())
    rows = list(
        (
            await session.execute(
                stmt.order_by(MedicalExam.valid_until.asc(), MedicalExam.exam_date.desc())
                .offset(offset)
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
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
            ("kind", exam_kind or ""),
            ("fitness", fitness or ""),
        ],
    )
    apply_etag_response_headers(response, etag)
    if request.headers.get("if-none-match") == etag:
        return Response(
            status_code=status.HTTP_304_NOT_MODIFIED,
            headers=build_not_modified_headers(etag),
        )
    return MedicalExamPage(
        items=[MedicalExamRead.model_validate(item) for item in rows], total=int(total or 0)
    )


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
        select(Person).where(
            Person.id == payload.person_id,
            Person.tenant_id == tenant.id,
            Person.deleted_at.is_(None),
        )
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


@router.post(
    "/medical/exams",
    response_model=MedicalExamRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[MedicalFeatureGate],
)
async def create_medical_exam(
    payload: MedicalExamCreate,
    tenant: TenantDep,
    session: SessionDep,
    access: MedicalAccess,
) -> MedicalExamRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    try:
        exam = await medsvc.record_exam(
            session,
            tenant_id=str(tenant.id),
            actor_id=getattr(access.user, "id", None),
            person_id=payload.person_id,
            exam_kind=payload.exam_kind,
            exam_date=payload.exam_date,
            fitness=payload.fitness,
            contraindications=payload.contraindications,
            conclusion=payload.conclusion,
            restrictions=payload.restrictions,
            valid_until=payload.valid_until,
            medical_org_name=payload.medical_org_name,
            referral_id=payload.referral_id,
            exam_type=payload.exam_type,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc))
    await session.commit()
    await session.refresh(exam)
    return MedicalExamRead.model_validate(exam)


@router.get(
    "/medical/exams/{exam_id}", response_model=MedicalExamRead, dependencies=[MedicalFeatureGate]
)
async def get_medical_exam(
    exam_id: str,
    tenant: TenantDep,
    session: SessionDep,
    access: MedicalReadAccess,
) -> MedicalExamRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    _ = access
    record = (
        await session.execute(
            select(MedicalExam).where(
                MedicalExam.id == exam_id,
                MedicalExam.tenant_id == tenant.id,
                MedicalExam.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if record is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=_error("medical_exam_not_found", "Medical exam not found"),
        )
    return MedicalExamRead.model_validate(record)


@router.patch(
    "/medical/exams/{exam_id}", response_model=MedicalExamRead, dependencies=[MedicalFeatureGate]
)
async def update_medical_exam(
    exam_id: str,
    payload: MedicalExamUpdate,
    tenant: TenantDep,
    session: SessionDep,
    access: MedicalAccess,
) -> MedicalExamRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    updates = payload.model_dump(exclude_unset=True)
    try:
        exam = await medsvc.update_exam(
            session,
            tenant_id=str(tenant.id),
            actor_id=getattr(access.user, "id", None),
            exam_id=exam_id,
            **updates,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc))
    await session.commit()
    await session.refresh(exam)
    return MedicalExamRead.model_validate(exam)


@router.get(
    "/medical/suspensions", response_model=MedicalSuspensionPage, dependencies=[MedicalFeatureGate]
)
async def list_suspensions(
    request: Request,
    response: Response,
    tenant: TenantDep,
    session: SessionDep,
    access: MedicalReadAccess,
    person_id: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
) -> MedicalSuspensionPage | Response:
    TenantContextValidator.ensure_tenant_context(tenant)
    _ = access
    stmt = select(MedicalSuspension).where(
        MedicalSuspension.tenant_id == tenant.id, MedicalSuspension.deleted_at.is_(None)
    )
    if person_id:
        stmt = stmt.where(MedicalSuspension.person_id == person_id)
    if status_filter == "active":
        stmt = stmt.where(MedicalSuspension.status == MedicalSuspensionStatus.ACTIVE)
    rows = list((await session.execute(stmt)).scalars().all())
    etag = compute_list_etag(
        tenant_id=str(tenant.id),
        items=rows,
        scalars=[
            ("total", len(rows)),
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
    return MedicalSuspensionPage(
        items=[MedicalSuspensionRead.model_validate(r) for r in rows], total=len(rows)
    )


# ---------------------------------------------------------------------------
# Task 6.5 — Suspension lift (admin/owner only)
# ---------------------------------------------------------------------------


@router.post(
    "/medical/suspensions/{suspension_id}/lift",
    response_model=MedicalSuspensionRead,
    dependencies=[MedicalFeatureGate],
)
async def lift_suspension(
    request: Request,
    suspension_id: str,
    tenant: TenantDep,
    session: SessionDep,
    access: MedicalAccess,
) -> MedicalSuspensionRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    roles = {v.lower() for v in access.to_auth_context().roles}
    if not roles & lc.LIFT_SUSPENSION_ROLES:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail=_error(
                "suspension_lift_forbidden", "Only admin or owner may lift a medical suspension"
            ),
        )
    record = (
        await session.execute(
            select(MedicalSuspension).where(
                MedicalSuspension.id == suspension_id,
                MedicalSuspension.tenant_id == tenant.id,
                MedicalSuspension.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if record is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail=_error("suspension_not_found", "Suspension not found")
        )
    if record.status == MedicalSuspensionStatus.ACTIVE:
        record.status = MedicalSuspensionStatus.LIFTED
        record.lifted_at = datetime.now(timezone.utc)
        record.lifted_by = getattr(access.user, "id", None)
        from app.services.events import EventType
        from app.services.outbox import OutboxService

        await OutboxService(session).enqueue(
            tenant_id=str(tenant.id),
            event_type=EventType.PERSON_REINSTATED.value,
            idempotency_key=f"person-reinstated:{record.id}",
            payload={
                "tenant_id": str(tenant.id),
                "actor_id": getattr(access.user, "id", None),
                "suspension_id": record.id,
                "person_id": record.person_id,
            },
        )
        audit = AuditService(session)
        ip = request.client.host if request.client else "unknown"
        await audit.log_event(
            tenant_id=str(tenant.id),
            action="lift",
            object_type="medical_suspension",
            object_id=record.id,
            user_id=getattr(access.user, "id", None),
            ip=ip,
            request_id=getattr(request.state, "trace_id", None),
            user_agent=request.headers.get("user-agent"),
            details={"person_id": record.person_id},
        )
    await session.commit()
    await session.refresh(record)
    return MedicalSuspensionRead.model_validate(record)


# ---------------------------------------------------------------------------
# Task 6.2 — Norms CRUD
# ---------------------------------------------------------------------------


@router.get("/medical/norms", response_model=MedicalNormPage, dependencies=[MedicalFeatureGate])
async def list_medical_norms(
    request: Request,
    response: Response,
    tenant: TenantDep,
    session: SessionDep,
    access: MedicalReadAccess,
    position_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> MedicalNormPage | Response:
    TenantContextValidator.ensure_tenant_context(tenant)
    _ = access
    stmt = select(MedicalNorm).where(MedicalNorm.tenant_id == tenant.id)
    if position_id:
        stmt = stmt.where(MedicalNorm.position_id == position_id)
    total_stmt = select(func.count()).select_from(stmt.subquery())
    stmt = stmt.order_by(MedicalNorm.created_at.desc()).offset(offset).limit(limit)
    items = list((await session.execute(stmt)).scalars().all())
    total = await session.scalar(total_stmt)
    etag = compute_list_etag(
        tenant_id=str(tenant.id),
        items=items,
        scalars=[
            ("total", int(total or 0)),
            ("limit", limit),
            ("offset", offset),
            ("position", position_id or ""),
        ],
    )
    apply_etag_response_headers(response, etag)
    if request.headers.get("if-none-match") == etag:
        return Response(
            status_code=status.HTTP_304_NOT_MODIFIED,
            headers=build_not_modified_headers(etag),
        )
    return MedicalNormPage(
        items=[MedicalNormRead.model_validate(r) for r in items],
        total=int(total or 0),
    )


@router.post(
    "/medical/norms",
    response_model=MedicalNormRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[MedicalFeatureGate],
)
async def create_medical_norm(
    request: Request,
    payload: MedicalNormCreate,
    tenant: TenantDep,
    session: SessionDep,
    access: MedicalAccess,
) -> MedicalNormRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    record = MedicalNorm(tenant_id=str(tenant.id), **payload.model_dump())
    session.add(record)
    await session.flush()
    audit = AuditService(session)
    ip = request.client.host if request.client else "unknown"
    await audit.log_event(
        tenant_id=str(tenant.id),
        action="create",
        object_type="medical_norm",
        object_id=record.id,
        user_id=getattr(access.user, "id", None),
        ip=ip,
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
    )
    await session.commit()
    await session.refresh(record)
    return MedicalNormRead.model_validate(record)


@router.get(
    "/medical/norms/{norm_id}", response_model=MedicalNormRead, dependencies=[MedicalFeatureGate]
)
async def get_medical_norm(
    norm_id: str,
    tenant: TenantDep,
    session: SessionDep,
    access: MedicalReadAccess,
) -> MedicalNormRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    _ = access
    record = await _get_norm(session, str(tenant.id), norm_id)
    return MedicalNormRead.model_validate(record)


@router.patch(
    "/medical/norms/{norm_id}", response_model=MedicalNormRead, dependencies=[MedicalFeatureGate]
)
async def update_medical_norm(
    request: Request,
    norm_id: str,
    payload: MedicalNormUpdate,
    tenant: TenantDep,
    session: SessionDep,
    access: MedicalAccess,
) -> MedicalNormRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    record = await _get_norm(session, str(tenant.id), norm_id)
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(record, k, v)
    audit = AuditService(session)
    ip = request.client.host if request.client else "unknown"
    await audit.log_event(
        tenant_id=str(tenant.id),
        action="update",
        object_type="medical_norm",
        object_id=record.id,
        user_id=getattr(access.user, "id", None),
        ip=ip,
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
    )
    await session.commit()
    await session.refresh(record)
    return MedicalNormRead.model_validate(record)


@router.delete(
    "/medical/norms/{norm_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[MedicalFeatureGate],
)
async def delete_medical_norm(
    request: Request,
    norm_id: str,
    tenant: TenantDep,
    session: SessionDep,
    access: MedicalAccess,
) -> Response:
    TenantContextValidator.ensure_tenant_context(tenant)
    record = await _get_norm(session, str(tenant.id), norm_id)
    audit = AuditService(session)
    ip = request.client.host if request.client else "unknown"
    await audit.log_event(
        tenant_id=str(tenant.id),
        action="delete",
        object_type="medical_norm",
        object_id=record.id,
        user_id=getattr(access.user, "id", None),
        ip=ip,
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
    )
    await session.delete(record)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Task 6.3 — Referrals
# ---------------------------------------------------------------------------


@router.get(
    "/medical/referrals", response_model=MedicalReferralPage, dependencies=[MedicalFeatureGate]
)
async def list_medical_referrals(
    request: Request,
    response: Response,
    tenant: TenantDep,
    session: SessionDep,
    access: MedicalReadAccess,
    person_id: str | None = Query(default=None),
    status_filter: MedicalReferralStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> MedicalReferralPage | Response:
    TenantContextValidator.ensure_tenant_context(tenant)
    _ = access
    today = datetime.now(timezone.utc).date()
    stmt = select(MedicalReferral).where(
        MedicalReferral.tenant_id == tenant.id,
        MedicalReferral.deleted_at.is_(None),
    )
    if person_id:
        stmt = stmt.where(MedicalReferral.person_id == person_id)
    if status_filter:
        stmt = stmt.where(MedicalReferral.status == status_filter)
    total_stmt = select(func.count()).select_from(stmt.subquery())
    stmt = stmt.order_by(MedicalReferral.created_at.desc()).offset(offset).limit(limit)
    items = list((await session.execute(stmt)).scalars().all())
    total = await session.scalar(total_stmt)
    etag = compute_list_etag(
        tenant_id=str(tenant.id),
        items=items,
        scalars=[
            ("total", int(total or 0)),
            ("limit", limit),
            ("offset", offset),
            ("person", person_id or ""),
            ("status", status_filter.value if status_filter else ""),
        ],
    )
    apply_etag_response_headers(response, etag)
    if request.headers.get("if-none-match") == etag:
        return Response(
            status_code=status.HTTP_304_NOT_MODIFIED,
            headers=build_not_modified_headers(etag),
        )
    return MedicalReferralPage(
        items=[_to_referral_read(r, today=today) for r in items],
        total=int(total or 0),
    )


@router.post(
    "/medical/referrals",
    response_model=MedicalReferralRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[MedicalFeatureGate],
)
async def create_medical_referral(
    request: Request,
    payload: MedicalReferralCreate,
    tenant: TenantDep,
    session: SessionDep,
    access: MedicalAccess,
) -> MedicalReferralRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    today = datetime.now(timezone.utc).date()
    person = (
        await session.execute(
            select(Person).where(
                Person.id == payload.person_id,
                Person.tenant_id == tenant.id,
                Person.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if person is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=_error("person_not_found", "Person not found"),
        )
    ref = await medsvc.issue_referral(
        session,
        tenant_id=str(tenant.id),
        person_id=payload.person_id,
        exam_kind=payload.exam_kind,
        due_at=payload.due_at,
        medical_org_name=payload.medical_org_name,
        issued_by=getattr(access.user, "id", None),
    )
    audit = AuditService(session)
    ip = request.client.host if request.client else "unknown"
    await audit.log_event(
        tenant_id=str(tenant.id),
        action="create",
        object_type="medical_referral",
        object_id=ref.id,
        user_id=getattr(access.user, "id", None),
        ip=ip,
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
    )
    await session.commit()
    await session.refresh(ref)
    return _to_referral_read(ref, today=today)


@router.get(
    "/medical/referrals/{referral_id}",
    response_model=MedicalReferralRead,
    dependencies=[MedicalFeatureGate],
)
async def get_medical_referral(
    referral_id: str,
    tenant: TenantDep,
    session: SessionDep,
    access: MedicalReadAccess,
) -> MedicalReferralRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    _ = access
    record = await _get_referral(session, str(tenant.id), referral_id)
    return _to_referral_read(record, today=datetime.now(timezone.utc).date())


@router.post(
    "/medical/referrals/{referral_id}/transition",
    response_model=MedicalReferralRead,
    dependencies=[MedicalFeatureGate],
)
async def transition_referral(
    request: Request,
    referral_id: str,
    payload: MedicalReferralTransition,
    tenant: TenantDep,
    session: SessionDep,
    access: MedicalAccess,
) -> MedicalReferralRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    record = await _get_referral(session, str(tenant.id), referral_id)
    current = record.status
    target = payload.to
    try:
        lc.validate_transition(current, target)
    except lc.InvalidTransition as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=_error("referral_invalid_transition", str(exc)),
        )
    if current == target:
        return _to_referral_read(record, today=datetime.now(timezone.utc).date())
    if lc.requires_result(target):
        effective = payload.result_exam_id or record.result_exam_id
        if not effective:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=_error(
                    "result_required", "A result exam is required to complete a referral"
                ),
            )
    if payload.result_exam_id is not None:
        exam = (
            await session.execute(
                select(MedicalExam).where(
                    MedicalExam.id == payload.result_exam_id,
                    MedicalExam.tenant_id == tenant.id,
                    MedicalExam.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if exam is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=_error(
                    "result_exam_not_found",
                    "result_exam_id does not reference an exam in this tenant",
                ),
            )
        record.result_exam_id = payload.result_exam_id
    record.status = target
    audit = AuditService(session)
    ip = request.client.host if request.client else "unknown"
    await audit.log_event(
        tenant_id=str(tenant.id),
        action="transition",
        object_type="medical_referral",
        object_id=record.id,
        user_id=getattr(access.user, "id", None),
        ip=ip,
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
        details={"from": current.value, "to": target.value},
    )
    await session.commit()
    await session.refresh(record)
    return _to_referral_read(record, today=datetime.now(timezone.utc).date())


# ---------------------------------------------------------------------------
# Task 6 — MedicalFactor CRUD + 29н document endpoints
# ---------------------------------------------------------------------------


@router.get("/medical/factors", response_model=MedicalFactorPage, dependencies=[MedicalFeatureGate])
async def list_medical_factors(
    tenant: TenantDep,
    session: SessionDep,
    access: MedicalReadAccess,
    category: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> MedicalFactorPage:
    TenantContextValidator.ensure_tenant_context(tenant)
    _ = access
    stmt = select(MedicalFactor).where(MedicalFactor.tenant_id == tenant.id)
    if category:
        stmt = stmt.where(MedicalFactor.category == category)
    total = await session.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = list(
        (await session.execute(stmt.order_by(MedicalFactor.code.asc()).offset(offset).limit(limit)))
        .scalars()
        .all()
    )
    return MedicalFactorPage(
        items=[MedicalFactorRead.model_validate(r) for r in rows],
        total=int(total or 0),
    )


@router.post(
    "/medical/factors",
    response_model=MedicalFactorRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[MedicalFeatureGate],
)
async def create_medical_factor(
    request: Request,
    payload: MedicalFactorCreate,
    tenant: TenantDep,
    session: SessionDep,
    access: MedicalAccess,
) -> MedicalFactorRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    dup = await session.scalar(
        select(MedicalFactor).where(
            MedicalFactor.tenant_id == tenant.id,
            MedicalFactor.code == payload.code,
        )
    )
    if dup is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=_error(
                "medical_factor_duplicate", f"Factor code already exists: {payload.code}"
            ),
        )
    data = payload.model_dump()
    data["exam_kinds"] = [k.value for k in payload.exam_kinds]
    record = MedicalFactor(tenant_id=str(tenant.id), **data)
    session.add(record)
    await session.flush()
    audit = AuditService(session)
    ip = request.client.host if request.client else "unknown"
    await audit.log_event(
        tenant_id=str(tenant.id),
        action="create",
        object_type="medical_factor",
        object_id=record.id,
        user_id=getattr(access.user, "id", None),
        ip=ip,
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
    )
    await session.commit()
    await session.refresh(record)
    return MedicalFactorRead.model_validate(record)


@router.get(
    "/medical/factors/{factor_id}",
    response_model=MedicalFactorRead,
    dependencies=[MedicalFeatureGate],
)
async def get_medical_factor(
    factor_id: str,
    tenant: TenantDep,
    session: SessionDep,
    access: MedicalReadAccess,
) -> MedicalFactorRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    _ = access
    return MedicalFactorRead.model_validate(await _get_factor(session, str(tenant.id), factor_id))


@router.patch(
    "/medical/factors/{factor_id}",
    response_model=MedicalFactorRead,
    dependencies=[MedicalFeatureGate],
)
async def update_medical_factor(
    request: Request,
    factor_id: str,
    payload: MedicalFactorUpdate,
    tenant: TenantDep,
    session: SessionDep,
    access: MedicalAccess,
) -> MedicalFactorRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    record = await _get_factor(session, str(tenant.id), factor_id)
    data = payload.model_dump(exclude_unset=True)
    if "exam_kinds" in data and data["exam_kinds"] is not None:
        data["exam_kinds"] = [k.value if hasattr(k, "value") else k for k in data["exam_kinds"]]
    for k, v in data.items():
        setattr(record, k, v)
    audit = AuditService(session)
    ip = request.client.host if request.client else "unknown"
    await audit.log_event(
        tenant_id=str(tenant.id),
        action="update",
        object_type="medical_factor",
        object_id=record.id,
        user_id=getattr(access.user, "id", None),
        ip=ip,
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
    )
    await session.commit()
    await session.refresh(record)
    return MedicalFactorRead.model_validate(record)


@router.delete(
    "/medical/factors/{factor_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[MedicalFeatureGate],
)
async def delete_medical_factor(
    request: Request,
    factor_id: str,
    tenant: TenantDep,
    session: SessionDep,
    access: MedicalAccess,
) -> Response:
    TenantContextValidator.ensure_tenant_context(tenant)
    record = await _get_factor(session, str(tenant.id), factor_id)
    audit = AuditService(session)
    ip = request.client.host if request.client else "unknown"
    await audit.log_event(
        tenant_id=str(tenant.id),
        action="delete",
        object_type="medical_factor",
        object_id=record.id,
        user_id=getattr(access.user, "id", None),
        ip=ip,
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
    )
    await session.delete(record)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/medical/contingent/register",
    response_model=ContingentRegisterPage,
    dependencies=[MedicalFeatureGate],
)
async def get_contingent_register(
    tenant: TenantDep,
    session: SessionDep,
    access: MedicalReadAccess,
) -> ContingentRegisterPage:
    TenantContextValidator.ensure_tenant_context(tenant)
    _ = access
    today = datetime.now(timezone.utc).date()
    rows = await medsvc.build_contingent_register(session, tenant_id=str(tenant.id), today=today)
    return ContingentRegisterPage(
        items=[ContingentRegisterRow(**r) for r in rows],
        total=len(rows),
    )


@router.get("/medical/named-list", response_model=NamedListPage, dependencies=[MedicalFeatureGate])
async def get_named_list(
    tenant: TenantDep,
    session: SessionDep,
    access: MedicalReadAccess,
) -> NamedListPage:
    TenantContextValidator.ensure_tenant_context(tenant)
    _ = access
    today = datetime.now(timezone.utc).date()
    rows = await medsvc.build_named_list(session, tenant_id=str(tenant.id), today=today)
    return NamedListPage(items=[NamedListRow(**r) for r in rows], total=len(rows))


# ---------------------------------------------------------------------------
# Task 6.4 — Contingent / generate / summary
# ---------------------------------------------------------------------------


@router.get("/medical/contingent", response_model=ContingentPage, dependencies=[MedicalFeatureGate])
async def get_medical_contingent(
    tenant: TenantDep,
    session: SessionDep,
    access: MedicalReadAccess,
    position_id: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
) -> ContingentPage:
    TenantContextValidator.ensure_tenant_context(tenant)
    _ = access
    today = datetime.now(timezone.utc).date()
    items = await medsvc.compute_contingent(
        session,
        tenant_id=str(tenant.id),
        today=today,
        position_id=position_id,
    )
    if status_filter:
        items = [it for it in items if it["status"] == status_filter]
    return ContingentPage(
        items=[ContingentItem(**i) for i in items],
        total=len(items),
    )


@router.post("/medical/contingent/generate-referrals", dependencies=[MedicalFeatureGate])
async def generate_referrals(
    request: Request,
    tenant: TenantDep,
    session: SessionDep,
    access: MedicalAccess,
) -> dict[str, int]:
    TenantContextValidator.ensure_tenant_context(tenant)
    today = datetime.now(timezone.utc).date()
    count = await medsvc.generate_due_referrals(
        session,
        tenant_id=str(tenant.id),
        today=today,
        issued_by=getattr(access.user, "id", None),
    )
    audit = AuditService(session)
    ip = request.client.host if request.client else "unknown"
    await audit.log_event(
        tenant_id=str(tenant.id),
        action="generate",
        object_type="medical_referral",
        object_id="bulk",
        user_id=getattr(access.user, "id", None),
        ip=ip,
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
        details={"count": count},
    )
    await session.commit()
    return {"count": count}


@router.get("/medical/summary", response_model=MedicalSummary, dependencies=[MedicalFeatureGate])
async def get_medical_summary(
    tenant: TenantDep,
    session: SessionDep,
    access: MedicalReadAccess,
) -> MedicalSummary:
    TenantContextValidator.ensure_tenant_context(tenant)
    _ = access
    today = datetime.now(timezone.utc).date()
    return MedicalSummary(
        **await medsvc.status_summary(session, tenant_id=str(tenant.id), today=today)
    )
