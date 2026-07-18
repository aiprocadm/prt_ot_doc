"""Medical endpoints — norms / referrals / factors CRUD (ARCH-4 slice 7 split)."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException, Query, Request, Response, status
from sqlalchemy import func, select

from app.api.helpers.etag import (
    apply_etag_response_headers,
    build_not_modified_headers,
    compute_list_etag,
)
from app.api.routes.medical._common import (
    MedicalAccess,
    MedicalFeatureGate,
    MedicalReadAccess,
    SessionDep,
    TenantDep,
    _error,
    _get_factor,
    _get_norm,
    _get_referral,
    _to_referral_read,
    router,
)
from app.core.tenant_validation import TenantContextValidator
from app.domains.medical import lifecycle as lc
from app.domains.medical import service as medsvc
from app.models.models import (
    MedicalExam,
    MedicalFactor,
    MedicalNorm,
    MedicalReferral,
    MedicalReferralStatus,
    Person,
)
from app.schemas.medical import (
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
)
from app.services.audit import AuditService


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
                    # The result exam must belong to the same person as the referral,
                    # else one person's referral could be closed with another's exam.
                    MedicalExam.person_id == record.person_id,
                    MedicalExam.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if exam is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=_error(
                    "result_exam_not_found",
                    "result_exam_id does not reference an exam for this referral's person",
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


# ---------------------------------------------------------------------------
# Task 6.x — Runtime hazard→factor mapping (RiskHazard.medical_factor_code)
# ---------------------------------------------------------------------------
