"""Medical endpoints — exams, requirements, suspensions (ARCH-4 slice 7 split)."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException, Query, Request, Response, status
from sqlalchemy import false as sa_false
from sqlalchemy import func, select

from app.api.dependencies_managed_client import ClientScopeDep
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
    router,
)
from app.core.audit_decorator import audit_operation
from app.core.tenant_validation import TenantContextValidator
from app.db.session import rearm_session_tenant_context
from app.domains.medical import lifecycle as lc
from app.domains.medical import service as medsvc
from app.models.models import (
    MedicalExam,
    MedicalSuspension,
    MedicalSuspensionStatus,
    Person,
)
from app.schemas.medical import (
    MedicalExamCreate,
    MedicalExamPage,
    MedicalExamRead,
    MedicalExamUpdate,
    MedicalRequirementCreate,
    MedicalSuspensionPage,
    MedicalSuspensionRead,
)
from app.schemas.task import TaskRead
from app.services.audit import AuditService
from app.services.obligations import create_medical_task


@router.get("/medical/exams", response_model=MedicalExamPage)
async def list_medical_exams(
    request: Request,
    response: Response,
    tenant: TenantDep,
    session: SessionDep,
    access: MedicalReadAccess,
    scope: ClientScopeDep,
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
    # Работа «от имени клиента» (BIZ-49 срез-9): медосмотр принадлежит клиенту
    # через сотрудника. Подзапросом, а не join'ом: пагинация и подсчёт итога
    # идут по той же выборке, а join размножил бы строки.
    if scope is not None:
        if not scope.visible:
            # Пусто, а не «все медосмотры арендатора»: сводка внимания уже
            # честно говорит, что данные такого клиента отсюда не читаются.
            stmt = stmt.where(sa_false())
        else:
            stmt = stmt.where(
                MedicalExam.person_id.in_(
                    select(Person.id).where(
                        Person.tenant_id == tenant.id,
                        Person.company_id == scope.company_id,
                        Person.deleted_at.is_(None),
                    )
                )
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
            # Без этого 304-й ответ отдал бы кэш, набранный вне контекста.
            ("managed_client", scope.client_id if scope else ""),
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
    # commit() drops the transaction-local RLS GUCs — re-arm before
    # further session work (SEC-65)
    await rearm_session_tenant_context(session)
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
            psychiatric_protocol_no=payload.psychiatric_protocol_no,
            psychiatric_activity_codes=payload.psychiatric_activity_codes,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc))
    await session.commit()
    # commit() drops the transaction-local RLS GUCs — re-arm before
    # further session work (SEC-65)
    await rearm_session_tenant_context(session)
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
    # commit() drops the transaction-local RLS GUCs — re-arm before
    # further session work (SEC-65)
    await rearm_session_tenant_context(session)
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
    # commit() drops the transaction-local RLS GUCs — re-arm before
    # further session work (SEC-65)
    await rearm_session_tenant_context(session)
    await session.refresh(record)
    return MedicalSuspensionRead.model_validate(record)


# ---------------------------------------------------------------------------
# Task 6.2 — Norms CRUD
# ---------------------------------------------------------------------------
