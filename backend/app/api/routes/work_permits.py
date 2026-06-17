# backend/app/api/routes/work_permits.py
"""Endpoints for work permits (наряды-допуски)."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.core.audit_decorator import audit_operation
from app.core.errors import api_problem_detail
from app.core.security import AccessContext, abac
from app.core.tenant_validation import TenantContextValidator
from app.domains.work_permits import lifecycle as lc
from app.domains.work_permits import (
    add_member, cancel, close, create_work_permit, delete_draft, extend, issue,
    list_events, list_members, remove_member, resume, suspend, update_work_permit,
)
from app.models.models import Person
from app.models.tenanting import Tenant
from app.models.work_permit import WorkPermit
from app.schemas.work_permit import (
    ReadinessReportRead, ViolationRead, WorkPermitActionRequest, WorkPermitCreate,
    WorkPermitEventRead, WorkPermitExtendRequest, WorkPermitMemberCreate,
    WorkPermitMemberRead, WorkPermitPage, WorkPermitRead, WorkPermitUpdate,
)
from app.services.work_permit_admission import WorkPermitBlocked, check_brigade_readiness

router = APIRouter(prefix="/work-permits")

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[Tenant, Depends(get_tenant_record)]


def _tenant_resource_id(tenant: Tenant = Depends(get_tenant_record)) -> str | None:
    return getattr(tenant, "id", None)


_READ_ROLES = ["admin"]
_WRITE_ROLES = ["admin"]
ReaderAccess = Annotated[AccessContext, Depends(abac(_tenant_resource_id, required_roles=_READ_ROLES))]
WriterAccess = Annotated[AccessContext, Depends(abac(_tenant_resource_id, required_roles=_WRITE_ROLES))]


def _transition_conflict(exc: lc.WorkPermitTransitionError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=api_problem_detail(
            code="WORK_PERMIT_TRANSITION_INVALID", message=str(exc), error_type="work_permit"
        ),
    )


def _member_schema(m) -> WorkPermitMemberRead:
    return WorkPermitMemberRead(id=str(m.id), person_id=str(m.person_id), role=m.role, created_at=m.created_at)


async def _permit_read(session: AsyncSession, tenant: Tenant, wp: WorkPermit) -> WorkPermitRead:
    members = await list_members(session, tenant_id=tenant.id, work_permit_id=wp.id)
    return WorkPermitRead(
        id=str(wp.id), number=wp.number, work_type=wp.work_type, zone_text=wp.zone_text,
        site_id=str(wp.site_id) if wp.site_id else None, equipment_text=wp.equipment_text,
        hazards_text=wp.hazards_text, measures_text=wp.measures_text,
        planned_start=wp.planned_start, planned_end=wp.planned_end, status=str(wp.status),
        opened_at=wp.opened_at, closed_at=wp.closed_at, suspended_at=wp.suspended_at,
        members=[_member_schema(m) for m in members],
        created_at=wp.created_at, updated_at=wp.updated_at,
    )


async def _get_or_404(session: AsyncSession, tenant: Tenant, wp_id: str) -> WorkPermit:
    stmt = select(WorkPermit).where(WorkPermit.id == wp_id, WorkPermit.tenant_id == tenant.id)
    wp = (await session.execute(stmt)).scalar_one_or_none()
    if wp is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "work permit not found")
    return wp


async def _ensure_person(session: AsyncSession, tenant: Tenant, person_id: str) -> None:
    stmt = select(Person.id).where(
        Person.id == person_id, Person.tenant_id == tenant.id, Person.deleted_at.is_(None)
    )
    if (await session.execute(stmt)).scalar_one_or_none() is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "person not found")


async def _ensure_file(session: AsyncSession, tenant: Tenant, file_id: str) -> None:
    from app.models.file import File
    stmt = select(File.id).where(File.id == file_id, File.tenant_id == tenant.id)
    if (await session.execute(stmt)).scalar_one_or_none() is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "file not found")


@router.get("", response_model=WorkPermitPage)
async def list_work_permits(
    tenant: TenantDep, session: SessionDep, access: ReaderAccess,
    status_filter: str | None = Query(None, alias="status"),
    site_id: str | None = None, work_type: str | None = None,
    limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
) -> WorkPermitPage:
    TenantContextValidator.ensure_tenant_context(tenant)
    stmt = select(WorkPermit).where(WorkPermit.tenant_id == tenant.id)
    count_stmt = select(func.count()).select_from(WorkPermit).where(WorkPermit.tenant_id == tenant.id)
    for col, val in (("status", status_filter), ("site_id", site_id), ("work_type", work_type)):
        if val:
            stmt = stmt.where(getattr(WorkPermit, col) == val)
            count_stmt = count_stmt.where(getattr(WorkPermit, col) == val)
    stmt = stmt.order_by(WorkPermit.created_at.desc()).limit(limit).offset(offset)
    rows = (await session.execute(stmt)).scalars().all()
    total = (await session.execute(count_stmt)).scalar_one()
    items = [await _permit_read(session, tenant, wp) for wp in rows]
    return WorkPermitPage(items=items, total=total)


@router.post("", response_model=WorkPermitRead, status_code=status.HTTP_201_CREATED)
@audit_operation("create", "work_permit")
async def create_work_permit_endpoint(
    payload: WorkPermitCreate, tenant: TenantDep, session: SessionDep, access: WriterAccess
) -> WorkPermitRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    wp = await create_work_permit(
        session, tenant_id=tenant.id, work_type=payload.work_type, zone_text=payload.zone_text,
        number=payload.number, site_id=payload.site_id, equipment_text=payload.equipment_text,
        hazards_text=payload.hazards_text, measures_text=payload.measures_text,
        planned_start=payload.planned_start, planned_end=payload.planned_end,
    )
    return await _permit_read(session, tenant, wp)


@router.get("/{wp_id}", response_model=WorkPermitRead)
async def get_work_permit(wp_id: str, tenant: TenantDep, session: SessionDep, access: ReaderAccess) -> WorkPermitRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    return await _permit_read(session, tenant, await _get_or_404(session, tenant, wp_id))


@router.patch("/{wp_id}", response_model=WorkPermitRead)
@audit_operation("update", "work_permit")
async def update_work_permit_endpoint(
    wp_id: str, payload: WorkPermitUpdate, tenant: TenantDep, session: SessionDep, access: WriterAccess
) -> WorkPermitRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _get_or_404(session, tenant, wp_id)
    fields = payload.model_dump(exclude_unset=True)
    if "site_id" in fields and fields["site_id"]:
        from app.models.models import Site
        ok = (await session.execute(select(Site.id).where(
            Site.id == fields["site_id"], Site.tenant_id == tenant.id, Site.deleted_at.is_(None)
        ))).scalar_one_or_none()
        if ok is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "site not found")
    try:
        wp = await update_work_permit(session, tenant_id=tenant.id, work_permit_id=wp_id, **fields)
    except lc.WorkPermitTransitionError as exc:
        raise _transition_conflict(exc) from exc
    return await _permit_read(session, tenant, wp)


@router.delete("/{wp_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
@audit_operation("delete", "work_permit")
async def delete_work_permit_endpoint(wp_id: str, tenant: TenantDep, session: SessionDep, access: WriterAccess):
    TenantContextValidator.ensure_tenant_context(tenant)
    await _get_or_404(session, tenant, wp_id)
    try:
        await delete_draft(session, tenant_id=tenant.id, work_permit_id=wp_id)
    except lc.WorkPermitTransitionError as exc:
        raise _transition_conflict(exc) from exc
    from fastapi import Response
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{wp_id}/members", response_model=WorkPermitMemberRead, status_code=status.HTTP_201_CREATED)
@audit_operation("update", "work_permit")
async def add_member_endpoint(
    wp_id: str, payload: WorkPermitMemberCreate, tenant: TenantDep, session: SessionDep, access: WriterAccess
) -> WorkPermitMemberRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _get_or_404(session, tenant, wp_id)
    await _ensure_person(session, tenant, payload.person_id)
    try:
        member = await add_member(
            session, tenant_id=tenant.id, work_permit_id=wp_id,
            person_id=payload.person_id, role=payload.role,
        )
    except lc.WorkPermitTransitionError as exc:
        raise _transition_conflict(exc) from exc
    return _member_schema(member)


@router.delete("/{wp_id}/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
@audit_operation("update", "work_permit")
async def remove_member_endpoint(
    wp_id: str, member_id: str, tenant: TenantDep, session: SessionDep, access: WriterAccess
):
    TenantContextValidator.ensure_tenant_context(tenant)
    await _get_or_404(session, tenant, wp_id)
    ok = await remove_member(session, tenant_id=tenant.id, work_permit_id=wp_id, member_id=member_id)
    if not ok:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "member not found")
    from fastapi import Response
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _blocked_conflict(exc: WorkPermitBlocked) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=api_problem_detail(
            code="WORK_PERMIT_BLOCKED",
            message="brigade readiness failed",
            error_type="work_permit",
            details={"violations": [
                {"person_id": v.person_id, "role": v.role, "code": v.code, "severity": v.severity}
                for v in exc.violations
            ]},
        ),
    )


async def _action(session, tenant, wp_id, coro_factory):
    await _get_or_404(session, tenant, wp_id)
    try:
        wp = await coro_factory()
    except lc.WorkPermitTransitionError as exc:
        raise _transition_conflict(exc) from exc
    except WorkPermitBlocked as exc:
        raise _blocked_conflict(exc) from exc
    return await _permit_read(session, tenant, wp)


@router.get("/{wp_id}/readiness", response_model=ReadinessReportRead)
async def readiness(wp_id: str, tenant: TenantDep, session: SessionDep, access: ReaderAccess) -> ReadinessReportRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _get_or_404(session, tenant, wp_id)
    report = await check_brigade_readiness(session, tenant_id=tenant.id, work_permit_id=wp_id)
    return ReadinessReportRead(
        ok=report.ok,
        violations=[ViolationRead(person_id=v.person_id, role=v.role, code=v.code, severity=v.severity)
                    for v in report.violations],
    )


@router.get("/{wp_id}/events", response_model=list[WorkPermitEventRead])
async def events(wp_id: str, tenant: TenantDep, session: SessionDep, access: ReaderAccess) -> list[WorkPermitEventRead]:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _get_or_404(session, tenant, wp_id)
    rows = await list_events(session, tenant_id=tenant.id, work_permit_id=wp_id)
    return [WorkPermitEventRead(
        id=str(e.id), event_type=e.event_type, at=e.at, actor_user_id=e.actor_user_id,
        photo_file_id=e.photo_file_id, note=e.note,
    ) for e in rows]


@router.post("/{wp_id}/issue", response_model=WorkPermitRead)
@audit_operation("update", "work_permit")
async def issue_endpoint(wp_id: str, payload: WorkPermitActionRequest, tenant: TenantDep, session: SessionDep, access: WriterAccess) -> WorkPermitRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    if payload.photo_file_id:
        await _ensure_file(session, tenant, payload.photo_file_id)
    return await _action(session, tenant, wp_id, lambda: issue(
        session, tenant_id=tenant.id, work_permit_id=wp_id,
        actor_user_id=access.user.id if access else None,
        photo_file_id=payload.photo_file_id, note=payload.note,
    ))


@router.post("/{wp_id}/suspend", response_model=WorkPermitRead)
@audit_operation("update", "work_permit")
async def suspend_endpoint(wp_id: str, payload: WorkPermitActionRequest, tenant: TenantDep, session: SessionDep, access: WriterAccess) -> WorkPermitRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    return await _action(session, tenant, wp_id, lambda: suspend(
        session, tenant_id=tenant.id, work_permit_id=wp_id,
        actor_user_id=access.user.id if access else None, note=payload.note,
    ))


@router.post("/{wp_id}/resume", response_model=WorkPermitRead)
@audit_operation("update", "work_permit")
async def resume_endpoint(wp_id: str, payload: WorkPermitActionRequest, tenant: TenantDep, session: SessionDep, access: WriterAccess) -> WorkPermitRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    return await _action(session, tenant, wp_id, lambda: resume(
        session, tenant_id=tenant.id, work_permit_id=wp_id,
        actor_user_id=access.user.id if access else None, note=payload.note,
    ))


@router.post("/{wp_id}/close", response_model=WorkPermitRead)
@audit_operation("update", "work_permit")
async def close_endpoint(wp_id: str, payload: WorkPermitActionRequest, tenant: TenantDep, session: SessionDep, access: WriterAccess) -> WorkPermitRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    if payload.photo_file_id:
        await _ensure_file(session, tenant, payload.photo_file_id)
    return await _action(session, tenant, wp_id, lambda: close(
        session, tenant_id=tenant.id, work_permit_id=wp_id,
        actor_user_id=access.user.id if access else None,
        photo_file_id=payload.photo_file_id, note=payload.note,
    ))


@router.post("/{wp_id}/cancel", response_model=WorkPermitRead)
@audit_operation("update", "work_permit")
async def cancel_endpoint(wp_id: str, payload: WorkPermitActionRequest, tenant: TenantDep, session: SessionDep, access: WriterAccess) -> WorkPermitRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    return await _action(session, tenant, wp_id, lambda: cancel(
        session, tenant_id=tenant.id, work_permit_id=wp_id,
        actor_user_id=access.user.id if access else None, note=payload.note,
    ))


@router.post("/{wp_id}/extend", response_model=WorkPermitRead)
@audit_operation("update", "work_permit")
async def extend_endpoint(wp_id: str, payload: WorkPermitExtendRequest, tenant: TenantDep, session: SessionDep, access: WriterAccess) -> WorkPermitRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    return await _action(session, tenant, wp_id, lambda: extend(
        session, tenant_id=tenant.id, work_permit_id=wp_id, planned_end=payload.planned_end,
        actor_user_id=access.user.id if access else None,
    ))
