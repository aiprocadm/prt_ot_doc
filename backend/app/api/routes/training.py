"""Training module endpoints (courses, plans, sessions, certificates)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_correlation_id, get_session, get_tenant_record
from app.core.audit_decorator import audit_operation
from app.core.security import AccessContext, abac
from app.domains.training import (
    assign_training_plan,
    issue_certificate,
    register_training_session,
    upcoming_certificate_expirations,
)
from app.models.file import File
from app.models.models import (
    Company,
    Person,
    Tenant,
    TrainingCourse,
    TrainingPlan,
    TrainingSessionStatus,
)
from app.schemas.training import (
    TrainingCertificateCreate,
    TrainingCertificatePage,
    TrainingCertificateRead,
    TrainingCourseCreate,
    TrainingCoursePage,
    TrainingCourseRead,
    TrainingCourseUpdate,
    TrainingPlanCreate,
    TrainingPlanRead,
    TrainingSessionCreate,
    TrainingSessionRead,
)
from app.services.events import EventType
from app.services.outbox import OutboxService
from app.core.permission_checker import PermissionChecker
from app.core.tenant_validation import TenantContextValidator

router = APIRouter(prefix="/training", tags=["training"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[Tenant, Depends(get_tenant_record)]

_TRAINING_READ_ROLES = ["admin"]
_TRAINING_WRITE_ROLES = ["admin"]


def _tenant_resource_id(tenant: Tenant = Depends(get_tenant_record)) -> str | None:
    return getattr(tenant, "id", None)


ManagerAccess = Annotated[
    AccessContext,
    Depends(abac(_tenant_resource_id, required_roles=_TRAINING_READ_ROLES)),
]
EditorAccess = Annotated[
    AccessContext,
    Depends(abac(_tenant_resource_id, required_roles=_TRAINING_WRITE_ROLES)),
]


def _training_bad_request(message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={"code": "training_validation_error", "message": message},
    )


def _course_to_schema(course: TrainingCourse) -> TrainingCourseRead:
    return TrainingCourseRead(
        id=course.id,
        title=course.title,
        code=course.code,
        description=course.description,
        duration_hours=course.duration_hours,
        valid_period_days=course.valid_period_days,
        metadata_json=course.metadata_json or {},
        created_at=course.created_at,
        updated_at=course.updated_at,
    )


async def _get_course(session: AsyncSession, tenant: Tenant, course_id: str) -> TrainingCourse:
    stmt = select(TrainingCourse).where(
        TrainingCourse.id == course_id,
        TrainingCourse.tenant_id == tenant.id,
        TrainingCourse.deleted_at.is_(None),
    )
    course = (await session.execute(stmt)).scalar_one_or_none()
    if course is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Course not found")
    return course


async def _get_company(session: AsyncSession, tenant: Tenant, company_id: str) -> Company:
    stmt = select(Company).where(
        Company.id == company_id,
        Company.tenant_id == tenant.id,
        Company.deleted_at.is_(None),
    )
    company = (await session.execute(stmt)).scalar_one_or_none()
    if company is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Company not found")
    return company


async def _get_person(session: AsyncSession, tenant: Tenant, person_id: str) -> Person:
    stmt = select(Person).where(
        Person.id == person_id,
        Person.tenant_id == tenant.id,
        Person.deleted_at.is_(None),
    )
    person = (await session.execute(stmt)).scalar_one_or_none()
    if person is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Person not found")
    return person


async def _get_plan(session: AsyncSession, tenant: Tenant, plan_id: str) -> TrainingPlan:
    stmt = select(TrainingPlan).where(
        TrainingPlan.id == plan_id,
        TrainingPlan.tenant_id == tenant.id,
        TrainingPlan.deleted_at.is_(None),
    )
    plan = (await session.execute(stmt)).scalar_one_or_none()
    if plan is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Training plan not found")
    return plan


@router.get("/courses", response_model=TrainingCoursePage)
async def list_courses(
    tenant: TenantDep,
    session: SessionDep,
    access: ManagerAccess,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> TrainingCoursePage:
    TenantContextValidator.ensure_tenant_context(tenant)

    stmt = (
        select(TrainingCourse)
        .where(TrainingCourse.tenant_id == tenant.id, TrainingCourse.deleted_at.is_(None))
        .order_by(TrainingCourse.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    items = (await session.execute(stmt)).scalars().all()
    total_stmt = select(func.count()).select_from(TrainingCourse).where(
        TrainingCourse.tenant_id == tenant.id, TrainingCourse.deleted_at.is_(None)
    )
    total = (await session.execute(total_stmt)).scalar_one()
    return TrainingCoursePage(items=[_course_to_schema(item) for item in items], total=total)


@router.post("/courses", response_model=TrainingCourseRead, status_code=status.HTTP_201_CREATED)
@audit_operation("create", "training_course")
async def create_course(
    payload: TrainingCourseCreate,
    tenant: TenantDep,
    session: SessionDep,
    access: EditorAccess,
) -> TrainingCourseRead:
    TenantContextValidator.ensure_tenant_context(tenant)

    course = TrainingCourse(
        tenant_id=tenant.id,
        title=payload.title.strip(),
        code=payload.code.strip() if payload.code else None,
        description=payload.description,
        duration_hours=payload.duration_hours,
        valid_period_days=payload.valid_period_days,
        metadata_json=payload.metadata_json,
    )
    session.add(course)
    await session.flush()
    await session.refresh(course)
    return _course_to_schema(course)


@router.get("/courses/{course_id}", response_model=TrainingCourseRead)
async def get_course(
    course_id: str,
    tenant: TenantDep,
    session: SessionDep,
    access: ManagerAccess,
) -> TrainingCourseRead:
    TenantContextValidator.ensure_tenant_context(tenant)

    course = await _get_course(session, tenant, course_id)
    return _course_to_schema(course)


@router.patch("/courses/{course_id}", response_model=TrainingCourseRead)
@audit_operation("update", "training_course")
async def update_course(
    course_id: str,
    payload: TrainingCourseUpdate,
    tenant: TenantDep,
    session: SessionDep,
    access: EditorAccess,
) -> TrainingCourseRead:
    TenantContextValidator.ensure_tenant_context(tenant)

    course = await _get_course(session, tenant, course_id)
    updates = payload.model_dump(exclude_unset=True, by_alias=True)
    for field, value in updates.items():
        if field == "metadata_json" and value is None:
            continue
        setattr(course, field, value)
    await session.flush()
    await session.refresh(course)
    return TrainingCourseRead.model_validate(course)


@router.delete(
    "/courses/{course_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
)
@audit_operation("delete", "training_course")
async def delete_course(
    course_id: str,
    tenant: TenantDep,
    session: SessionDep,
    access: EditorAccess,
) -> None:
    TenantContextValidator.ensure_tenant_context(tenant)

    course = await _get_course(session, tenant, course_id)
    course.deleted_at = datetime.now(tz=timezone.utc)
    await session.flush()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/plans", response_model=TrainingPlanRead, status_code=status.HTTP_201_CREATED)
@audit_operation("assign", "training_plan")
async def assign_plan(
    payload: TrainingPlanCreate,
    tenant: TenantDep,
    session: SessionDep,
    access: EditorAccess,
) -> TrainingPlanRead:
    TenantContextValidator.ensure_tenant_context(tenant)

    await _get_company(session, tenant, payload.company_id)
    try:
        plan = await assign_training_plan(
            session,
            tenant_id=tenant.id,
            company_id=payload.company_id,
            course_id=payload.course_id,
            position_id=payload.position_id,
            person_id=payload.person_id,
            due_date=payload.due_date,
            is_mandatory=payload.is_mandatory,
            actor_id=access.user.id if access else None,
        )
    except ValueError as exc:
        raise _training_bad_request(str(exc)) from exc
    return TrainingPlanRead.model_validate(plan)


@router.get("/plans/{plan_id}", response_model=TrainingPlanRead)
async def get_plan(
    plan_id: str,
    tenant: TenantDep,
    session: SessionDep,
    access: ManagerAccess,
) -> TrainingPlanRead:
    TenantContextValidator.ensure_tenant_context(tenant)

    plan = await _get_plan(session, tenant, plan_id)
    return TrainingPlanRead.model_validate(plan)


@router.post("/sessions", response_model=TrainingSessionRead, status_code=status.HTTP_201_CREATED)
@audit_operation("create", "training_session")
async def create_session(
    payload: TrainingSessionCreate,
    tenant: TenantDep,
    session: SessionDep,
    access: EditorAccess,
) -> TrainingSessionRead:
    TenantContextValidator.ensure_tenant_context(tenant)

    try:
        record = await register_training_session(
            session,
            tenant_id=tenant.id,
            person_id=payload.person_id,
            course_id=payload.course_id,
            plan_id=payload.plan_id,
            status=payload.status,
            started_at=payload.started_at,
            completed_at=payload.completed_at,
            score=payload.score,
            notes=payload.notes,
        )
    except ValueError as exc:
        raise _training_bad_request(str(exc)) from exc
    if record.status == TrainingSessionStatus.COMPLETED:
        outbox = OutboxService(session)
        await outbox.enqueue(
            tenant_id=str(tenant.id),
            event_type=EventType.TRAINING_COMPLETED.value,
            payload={
                "tenant_id": str(tenant.id),
                "actor_id": access.user.id if access else None,
                "occurred_at": record.completed_at or datetime.now(tz=timezone.utc),
                "training_event_id": record.id,
                "session_id": record.id,
                "person_id": record.person_id,
                "course_id": record.course_id,
                "plan_id": record.plan_id,
                "completed_at": record.completed_at,
                "status": record.status.value,
                "score": record.score,
            },
        )
    return TrainingSessionRead.model_validate(record)


@router.post("/certificates", response_model=TrainingCertificateRead, status_code=status.HTTP_201_CREATED)
@audit_operation("create", "training_certificate")
async def create_certificate(
    payload: TrainingCertificateCreate,
    tenant: TenantDep,
    session: SessionDep,
    access: EditorAccess,
) -> TrainingCertificateRead:
    TenantContextValidator.ensure_tenant_context(tenant)

    if payload.file_id:
        file_stmt = select(File).where(File.id == payload.file_id, File.tenant_id == tenant.id)
        file = (await session.execute(file_stmt)).scalar_one_or_none()
        if file is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found")

    try:
        result = await issue_certificate(
            session,
            tenant_id=tenant.id,
            person_id=payload.person_id,
            course_id=payload.course_id,
            plan_id=payload.plan_id,
            session_id=payload.session_id,
            file_id=payload.file_id,
            number=payload.number,
            issued_at=payload.issued_at,
            valid_until=payload.valid_until,
            permit_type=payload.permit_type,
            position_id=payload.position_id,
        )
    except ValueError as exc:
        raise _training_bad_request(str(exc)) from exc

    return TrainingCertificateRead.model_validate(result.certificate)


@router.get("/certificates/expiring", response_model=TrainingCertificatePage)
async def list_expiring_certificates(
    tenant: TenantDep,
    session: SessionDep,
    access: ManagerAccess,
    within_days: int = Query(30, ge=1, le=365),
) -> TrainingCertificatePage:
    TenantContextValidator.ensure_tenant_context(tenant)

    cutoff = date.today() + timedelta(days=within_days)
    certificates = await upcoming_certificate_expirations(session, tenant_id=tenant.id, before=cutoff)
    items = [TrainingCertificateRead.model_validate(item) for item in certificates]
    return TrainingCertificatePage(items=items, total=len(items))
