"""Medical endpoints — 342н psychiatric assessment: 695 activity-type catalog + seed-defaults
+ должность→вид mapping. Behind the medical feature flag; same RBAC as the rest of /medical."""

from __future__ import annotations

from fastapi import HTTPException, Query, Request, Response, status
from sqlalchemy import delete, func, select

from app.api.routes.medical._common import (
    MedicalAccess,
    MedicalFeatureGate,
    MedicalReadAccess,
    SessionDep,
    TenantDep,
    _error,
    _get_activity_type,
    router,
)
from app.core.tenant_validation import TenantContextValidator
from app.domains.medical import service as medsvc
from app.models.models import (
    Position,
    PsychiatricActivityType,
    PsychiatricPositionActivity,
)
from app.schemas.medical import (
    PositionActivitiesIn,
    PositionActivitiesPage,
    PositionActivitiesRead,
    PsychiatricActivityTypeCreate,
    PsychiatricActivityTypePage,
    PsychiatricActivityTypeRead,
    PsychiatricActivityTypeUpdate,
)
from app.services.audit import AuditService


def _audit_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


# --- activity-type catalog CRUD ---


@router.get(
    "/medical/psychiatric/activity-types",
    response_model=PsychiatricActivityTypePage,
    dependencies=[MedicalFeatureGate],
)
async def list_activity_types(
    tenant: TenantDep,
    session: SessionDep,
    access: MedicalReadAccess,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> PsychiatricActivityTypePage:
    TenantContextValidator.ensure_tenant_context(tenant)
    _ = access
    stmt = select(PsychiatricActivityType).where(PsychiatricActivityType.tenant_id == tenant.id)
    total = await session.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = list(
        (
            await session.execute(
                stmt.order_by(PsychiatricActivityType.code.asc()).offset(offset).limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return PsychiatricActivityTypePage(
        items=[PsychiatricActivityTypeRead.model_validate(r) for r in rows],
        total=int(total or 0),
    )


@router.post(
    "/medical/psychiatric/activity-types",
    response_model=PsychiatricActivityTypeRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[MedicalFeatureGate],
)
async def create_activity_type(
    request: Request,
    payload: PsychiatricActivityTypeCreate,
    tenant: TenantDep,
    session: SessionDep,
    access: MedicalAccess,
) -> PsychiatricActivityTypeRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    dup = await session.scalar(
        select(PsychiatricActivityType).where(
            PsychiatricActivityType.tenant_id == tenant.id,
            PsychiatricActivityType.code == payload.code,
        )
    )
    if dup is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=_error(
                "activity_type_duplicate", f"Activity code already exists: {payload.code}"
            ),
        )
    record = PsychiatricActivityType(tenant_id=str(tenant.id), **payload.model_dump())
    session.add(record)
    await session.flush()
    audit = AuditService(session)
    await audit.log_event(
        tenant_id=str(tenant.id),
        action="create",
        object_type="psychiatric_activity_type",
        object_id=record.id,
        user_id=getattr(access.user, "id", None),
        ip=_audit_ip(request),
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
    )
    await session.commit()
    await session.refresh(record)
    return PsychiatricActivityTypeRead.model_validate(record)


@router.post(
    "/medical/psychiatric/activity-types/seed-defaults",
    dependencies=[MedicalFeatureGate],
)
async def seed_activity_type_defaults(
    request: Request,
    tenant: TenantDep,
    session: SessionDep,
    access: MedicalAccess,
) -> dict[str, int]:
    TenantContextValidator.ensure_tenant_context(tenant)
    count = await medsvc.seed_default_activity_types(session, tenant_id=str(tenant.id))
    audit = AuditService(session)
    await audit.log_event(
        tenant_id=str(tenant.id),
        action="seed",
        object_type="psychiatric_activity_type",
        object_id="defaults",
        user_id=getattr(access.user, "id", None),
        ip=_audit_ip(request),
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
        details={"count": count},
    )
    await session.commit()
    return {"count": count}


@router.get(
    "/medical/psychiatric/activity-types/{activity_id}",
    response_model=PsychiatricActivityTypeRead,
    dependencies=[MedicalFeatureGate],
)
async def get_activity_type(
    activity_id: str,
    tenant: TenantDep,
    session: SessionDep,
    access: MedicalReadAccess,
) -> PsychiatricActivityTypeRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    _ = access
    return PsychiatricActivityTypeRead.model_validate(
        await _get_activity_type(session, str(tenant.id), activity_id)
    )


@router.patch(
    "/medical/psychiatric/activity-types/{activity_id}",
    response_model=PsychiatricActivityTypeRead,
    dependencies=[MedicalFeatureGate],
)
async def update_activity_type(
    request: Request,
    activity_id: str,
    payload: PsychiatricActivityTypeUpdate,
    tenant: TenantDep,
    session: SessionDep,
    access: MedicalAccess,
) -> PsychiatricActivityTypeRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    record = await _get_activity_type(session, str(tenant.id), activity_id)
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(record, k, v)
    audit = AuditService(session)
    await audit.log_event(
        tenant_id=str(tenant.id),
        action="update",
        object_type="psychiatric_activity_type",
        object_id=record.id,
        user_id=getattr(access.user, "id", None),
        ip=_audit_ip(request),
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
    )
    await session.commit()
    await session.refresh(record)
    return PsychiatricActivityTypeRead.model_validate(record)


@router.delete(
    "/medical/psychiatric/activity-types/{activity_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[MedicalFeatureGate],
)
async def delete_activity_type(
    request: Request,
    activity_id: str,
    tenant: TenantDep,
    session: SessionDep,
    access: MedicalAccess,
) -> Response:
    TenantContextValidator.ensure_tenant_context(tenant)
    record = await _get_activity_type(session, str(tenant.id), activity_id)
    audit = AuditService(session)
    await audit.log_event(
        tenant_id=str(tenant.id),
        action="delete",
        object_type="psychiatric_activity_type",
        object_id=record.id,
        user_id=getattr(access.user, "id", None),
        ip=_audit_ip(request),
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
    )
    await session.delete(record)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- position → activity mapping ---


async def _position_codes(session, tenant_id: str, position_id: str) -> list[str]:
    rows = (
        await session.execute(
            select(PsychiatricPositionActivity.activity_code).where(
                PsychiatricPositionActivity.tenant_id == tenant_id,
                PsychiatricPositionActivity.position_id == position_id,
            )
        )
    ).all()
    return sorted(c for (c,) in rows)


@router.get(
    "/medical/psychiatric/position-activities",
    response_model=PositionActivitiesPage,
    dependencies=[MedicalFeatureGate],
)
async def list_position_activities(
    tenant: TenantDep,
    session: SessionDep,
    access: MedicalReadAccess,
) -> PositionActivitiesPage:
    TenantContextValidator.ensure_tenant_context(tenant)
    _ = access
    rows = (
        await session.execute(
            select(
                PsychiatricPositionActivity.position_id,
                PsychiatricPositionActivity.activity_code,
            ).where(PsychiatricPositionActivity.tenant_id == tenant.id)
        )
    ).all()
    grouped: dict[str, list[str]] = {}
    for pos_id, code in rows:
        grouped.setdefault(pos_id, []).append(code)
    items = [
        PositionActivitiesRead(position_id=pid, activity_codes=sorted(codes))
        for pid, codes in grouped.items()
    ]
    return PositionActivitiesPage(items=items, total=len(items))


@router.put(
    "/medical/psychiatric/positions/{position_id}/activities",
    response_model=PositionActivitiesRead,
    dependencies=[MedicalFeatureGate],
)
async def set_position_activities(
    request: Request,
    position_id: str,
    payload: PositionActivitiesIn,
    tenant: TenantDep,
    session: SessionDep,
    access: MedicalAccess,
) -> PositionActivitiesRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    tid = str(tenant.id)
    # position must exist in tenant
    pos = await session.scalar(
        select(Position).where(Position.id == position_id, Position.tenant_id == tid)
    )
    if pos is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail=_error("position_not_found", "Position not found")
        )
    codes = list(dict.fromkeys(payload.activity_codes))  # dedupe, preserve order
    if codes:
        known = {
            c
            for (c,) in (
                await session.execute(
                    select(PsychiatricActivityType.code).where(
                        PsychiatricActivityType.tenant_id == tid,
                        PsychiatricActivityType.code.in_(tuple(codes)),
                    )
                )
            ).all()
        }
        unknown = [c for c in codes if c not in known]
        if unknown:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=_error(
                    "activity_code_unknown", f"Unknown activity codes: {', '.join(unknown)}"
                ),
            )
    # replace semantics: clear then insert
    await session.execute(
        delete(PsychiatricPositionActivity).where(
            PsychiatricPositionActivity.tenant_id == tid,
            PsychiatricPositionActivity.position_id == position_id,
        )
    )
    for code in codes:
        session.add(
            PsychiatricPositionActivity(tenant_id=tid, position_id=position_id, activity_code=code)
        )
    audit = AuditService(session)
    await audit.log_event(
        tenant_id=tid,
        action="update",
        object_type="psychiatric_position_activity",
        object_id=position_id,
        user_id=getattr(access.user, "id", None),
        ip=_audit_ip(request),
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
        details={"activity_codes": codes},
    )
    await session.commit()
    return PositionActivitiesRead(
        position_id=position_id, activity_codes=await _position_codes(session, tid, position_id)
    )
