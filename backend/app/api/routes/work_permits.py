# backend/app/api/routes/work_permits.py
"""Endpoints for work permits (наряды-допуски)."""
from __future__ import annotations

from typing import Annotated, Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.core.audit_decorator import audit_operation
from app.core.errors import api_problem_detail
from app.core.security import AccessContext, abac
from app.core.tenant_validation import TenantContextValidator
from app.domains.work_permits import lifecycle as lc
from app.domains.work_permits import profiles as wp_profiles
from app.domains.work_permits import (
    add_member, cancel, close, create_admission, create_briefing, create_work_permit,
    delete_draft, extend, get_admission, get_briefing, issue, list_admissions, list_briefings,
    list_events, list_members, remove_member, resume, suspend, update_admission, update_briefing,
    update_work_permit,
)
from app.domains.work_permits.service import record_completion, signed_closing_kinds
from app.domains.work_permits.signing import sign_briefing, sign_closing, sign_permit
from app.models.models import Person, SignatureRequest
from app.services.pep_signing import PepConflict, PepNotFound
from app.models.tenanting import Tenant
from app.models.work_permit import WorkPermit
from app.schemas.work_permit import (
    ReadinessReportRead, ViolationRead, WorkPermitActionRequest, WorkPermitBriefingCreate,
    WorkPermitBriefingRead, WorkPermitBriefingUpdate, WorkPermitClosingRecordCreate,
    WorkPermitClosingSummary, WorkPermitCreate,
    WorkPermitDailyAdmissionCreate, WorkPermitDailyAdmissionRead, WorkPermitDailyAdmissionUpdate,
    WorkPermitEventRead, WorkPermitExtendRequest, WorkPermitMemberCreate, WorkPermitMemberRead,
    WorkPermitPage, WorkPermitRead, WorkPermitSignatureCreate, WorkPermitSignatureRead,
    WorkPermitUpdate,
)
from app.services.work_permit_admission import WorkPermitBlocked, check_brigade_readiness
from app.services.work_permit_print import PdfRendererUnavailable, render_work_permit

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


def _briefing_read(br) -> WorkPermitBriefingRead:
    return WorkPermitBriefingRead(
        id=str(br.id), work_permit_id=str(br.work_permit_id),
        conducted_by_person_id=str(br.conducted_by_person_id) if br.conducted_by_person_id else None,
        conducted_at=br.conducted_at, topics_text=br.topics_text,
        created_at=br.created_at, updated_at=br.updated_at,
    )


def _pep_to_http(exc: Exception) -> HTTPException:
    if isinstance(exc, PepNotFound):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=api_problem_detail(code="PEP_NOT_FOUND", message=str(exc), error_type="work_permit"),
        )
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=api_problem_detail(code="PEP_CONFLICT", message=str(exc), error_type="work_permit"),
    )


def _signature_read(row: SignatureRequest, stream: str, *, confirm_code: str | None = None) -> WorkPermitSignatureRead:
    return WorkPermitSignatureRead(
        id=str(row.id), stream=stream, object_type=row.object_type, object_id=str(row.object_id),
        purpose=row.purpose, status=row.status,
        signer_person_id=str(row.signer_person_id) if row.signer_person_id else None,
        signer_name=row.signer_name, content_hash=row.content_hash, signed_at=row.signed_at,
        confirm_code=confirm_code,
    )


async def _closing_summary(session: AsyncSession, tenant: Tenant, wp: WorkPermit) -> WorkPermitClosingSummary:
    rows = (await session.execute(
        select(SignatureRequest).where(
            SignatureRequest.tenant_id == tenant.id,
            SignatureRequest.signature_type == "pep",
            SignatureRequest.object_type == "work_permit_closing",
            SignatureRequest.object_id == wp.id,
        ).order_by(SignatureRequest.created_at.asc())
    )).scalars().all()
    signed = await signed_closing_kinds(session, tenant_id=str(tenant.id), work_permit_id=str(wp.id))
    readiness = lc.closing_readiness(completion_text=wp.completion_text, signed_kinds=signed)
    return WorkPermitClosingSummary(
        completion_text=wp.completion_text,
        completion_recorded_at=wp.completion_recorded_at,
        signatures=[_signature_read(r, "closing") for r in rows],
        can_close=readiness.can_close,
        missing=readiness.missing,
    )


async def _permit_read(session: AsyncSession, tenant: Tenant, wp: WorkPermit) -> WorkPermitRead:
    members = await list_members(session, tenant_id=tenant.id, work_permit_id=wp.id)
    return WorkPermitRead(
        id=str(wp.id), number=wp.number, work_type=wp.work_type, zone_text=wp.zone_text,
        site_id=str(wp.site_id) if wp.site_id else None, equipment_text=wp.equipment_text,
        hazards_text=wp.hazards_text, measures_text=wp.measures_text,
        planned_start=wp.planned_start, planned_end=wp.planned_end, status=str(wp.status),
        opened_at=wp.opened_at, closed_at=wp.closed_at, suspended_at=wp.suspended_at,
        members=[_member_schema(m) for m in members],
        subdivision_text=wp.subdivision_text, content_text=wp.content_text,
        conditions_text=wp.conditions_text, safety_systems=wp.safety_systems,
        measures_before_text=wp.measures_before_text, measures_during_text=wp.measures_during_text,
        special_conditions_text=wp.special_conditions_text, ppe_text=wp.ppe_text,
        type_specific=wp.type_specific,
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
        subdivision_text=payload.subdivision_text, content_text=payload.content_text,
        conditions_text=payload.conditions_text, safety_systems=payload.safety_systems,
        measures_before_text=payload.measures_before_text,
        measures_during_text=payload.measures_during_text,
        special_conditions_text=payload.special_conditions_text, ppe_text=payload.ppe_text,
        type_specific=payload.type_specific,
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
    if "type_specific" in fields:
        effective_type = fields.get("work_type") or (
            await _get_or_404(session, tenant, wp_id)).work_type
        try:
            wp_profiles.validate_type_specific(effective_type, fields["type_specific"])
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
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
            actor_user_id=access.user.id if access else None,
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
    try:
        ok = await remove_member(
            session, tenant_id=tenant.id, work_permit_id=wp_id, member_id=member_id,
            actor_user_id=access.user.id if access else None,
        )
    except lc.WorkPermitTransitionError as exc:
        raise _transition_conflict(exc) from exc
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
        photo_file_id=e.photo_file_id, note=e.note, meta=e.meta,
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
    try:
        return await _action(session, tenant, wp_id, lambda: close(
            session, tenant_id=tenant.id, work_permit_id=wp_id,
            actor_user_id=access.user.id if access else None,
            photo_file_id=payload.photo_file_id, note=payload.note,
        ))
    except lc.WorkPermitClosingIncomplete as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=api_problem_detail(
                code="WORK_PERMIT_CLOSING_INCOMPLETE",
                message="closing requirements not met",
                error_type="work_permit",
                details={"missing": exc.missing},
            ),
        ) from exc


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


# --- Briefing endpoints (Ф2) -----------------------------------------------

@router.post("/{wp_id}/briefing", response_model=WorkPermitBriefingRead, status_code=status.HTTP_201_CREATED)
@audit_operation("update", "work_permit")
async def create_briefing_endpoint(
    wp_id: str, payload: WorkPermitBriefingCreate, tenant: TenantDep, session: SessionDep, access: WriterAccess
) -> WorkPermitBriefingRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _get_or_404(session, tenant, wp_id)
    if payload.conducted_by_person_id:
        await _ensure_person(session, tenant, payload.conducted_by_person_id)
    br = await create_briefing(
        session, tenant_id=tenant.id, work_permit_id=wp_id,
        conducted_by_person_id=payload.conducted_by_person_id,
        conducted_at=payload.conducted_at, topics_text=payload.topics_text,
    )
    if br is None:  # race: permit deleted between the check above and create
        raise HTTPException(status.HTTP_404_NOT_FOUND, "work permit not found")
    return _briefing_read(br)


@router.get("/{wp_id}/briefing", response_model=list[WorkPermitBriefingRead])
async def list_briefings_endpoint(
    wp_id: str, tenant: TenantDep, session: SessionDep, access: ReaderAccess
) -> list[WorkPermitBriefingRead]:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _get_or_404(session, tenant, wp_id)
    rows = await list_briefings(session, tenant_id=tenant.id, work_permit_id=wp_id)
    return [_briefing_read(b) for b in rows]


@router.patch("/{wp_id}/briefing/{briefing_id}", response_model=WorkPermitBriefingRead)
@audit_operation("update", "work_permit")
async def update_briefing_endpoint(
    wp_id: str, briefing_id: str, payload: WorkPermitBriefingUpdate,
    tenant: TenantDep, session: SessionDep, access: WriterAccess,
) -> WorkPermitBriefingRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _get_or_404(session, tenant, wp_id)
    fields = payload.model_dump(exclude_unset=True)
    if fields.get("conducted_by_person_id"):
        await _ensure_person(session, tenant, fields["conducted_by_person_id"])
    # briefing must belong to THIS permit (not just the same tenant)
    existing = await get_briefing(session, tenant_id=tenant.id, briefing_id=briefing_id)
    if existing is None or str(existing.work_permit_id) != wp_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "briefing not found")
    br = await update_briefing(session, tenant_id=tenant.id, briefing_id=briefing_id, **fields)
    return _briefing_read(br)


# --- Daily admission endpoints (Ф3a) ----------------------------------------

def _admission_read(a) -> WorkPermitDailyAdmissionRead:
    return WorkPermitDailyAdmissionRead(
        id=str(a.id), work_permit_id=str(a.work_permit_id), admission_date=a.admission_date,
        start_at=a.start_at, end_at=a.end_at,
        admitted_by_person_id=str(a.admitted_by_person_id) if a.admitted_by_person_id else None,
        note=a.note, created_at=a.created_at, updated_at=a.updated_at,
    )


@router.post("/{wp_id}/admissions", response_model=WorkPermitDailyAdmissionRead, status_code=status.HTTP_201_CREATED)
@audit_operation("update", "work_permit")
async def create_admission_endpoint(
    wp_id: str, payload: WorkPermitDailyAdmissionCreate, tenant: TenantDep, session: SessionDep, access: WriterAccess
) -> WorkPermitDailyAdmissionRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _get_or_404(session, tenant, wp_id)
    if payload.admitted_by_person_id:
        await _ensure_person(session, tenant, payload.admitted_by_person_id)
    try:
        adm = await create_admission(
            session, tenant_id=tenant.id, work_permit_id=wp_id,
            admission_date=payload.admission_date, start_at=payload.start_at, end_at=payload.end_at,
            admitted_by_person_id=payload.admitted_by_person_id, note=payload.note,
            actor_user_id=access.user.id if access else None,
        )
    except lc.WorkPermitTransitionError as exc:
        raise _transition_conflict(exc) from exc
    if adm is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "work permit not found")
    return _admission_read(adm)


@router.get("/{wp_id}/admissions", response_model=list[WorkPermitDailyAdmissionRead])
async def list_admissions_endpoint(
    wp_id: str, tenant: TenantDep, session: SessionDep, access: ReaderAccess
) -> list[WorkPermitDailyAdmissionRead]:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _get_or_404(session, tenant, wp_id)
    rows = await list_admissions(session, tenant_id=tenant.id, work_permit_id=wp_id)
    return [_admission_read(a) for a in rows]


@router.patch("/{wp_id}/admissions/{admission_id}", response_model=WorkPermitDailyAdmissionRead)
@audit_operation("update", "work_permit")
async def update_admission_endpoint(
    wp_id: str, admission_id: str, payload: WorkPermitDailyAdmissionUpdate,
    tenant: TenantDep, session: SessionDep, access: WriterAccess,
) -> WorkPermitDailyAdmissionRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _get_or_404(session, tenant, wp_id)
    fields = payload.model_dump(exclude_unset=True)
    if fields.get("admitted_by_person_id"):
        await _ensure_person(session, tenant, fields["admitted_by_person_id"])
    # admission must belong to THIS permit (not just the same tenant)
    existing = await get_admission(session, tenant_id=tenant.id, admission_id=admission_id)
    if existing is None or str(existing.work_permit_id) != wp_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "admission not found")
    adm = await update_admission(session, tenant_id=tenant.id, admission_id=admission_id, **fields)
    return _admission_read(adm)


# --- Signature endpoints (Ф2) -----------------------------------------------

@router.post("/{wp_id}/signatures", response_model=WorkPermitSignatureRead, status_code=status.HTTP_201_CREATED)
@audit_operation("update", "work_permit")
async def create_permit_signature_endpoint(
    wp_id: str, payload: WorkPermitSignatureCreate, tenant: TenantDep, session: SessionDep, access: WriterAccess
) -> WorkPermitSignatureRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _get_or_404(session, tenant, wp_id)
    await _ensure_person(session, tenant, payload.person_id)
    try:
        req, code = await sign_permit(
            session, tenant_id=str(tenant.id), work_permit_id=wp_id,
            person_id=payload.person_id, mode=payload.mode,
            requested_by=access.user.id if access else "system",
        )
    except (PepNotFound, PepConflict) as exc:
        raise _pep_to_http(exc) from exc
    return _signature_read(req, "permit", confirm_code=code)


@router.post(
    "/{wp_id}/briefing/{briefing_id}/signatures",
    response_model=WorkPermitSignatureRead, status_code=status.HTTP_201_CREATED,
)
@audit_operation("update", "work_permit")
async def create_briefing_signature_endpoint(
    wp_id: str, briefing_id: str, payload: WorkPermitSignatureCreate,
    tenant: TenantDep, session: SessionDep, access: WriterAccess,
) -> WorkPermitSignatureRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _get_or_404(session, tenant, wp_id)
    await _ensure_person(session, tenant, payload.person_id)
    # briefing must belong to THIS permit (not just the same tenant)
    existing = await get_briefing(session, tenant_id=tenant.id, briefing_id=briefing_id)
    if existing is None or str(existing.work_permit_id) != wp_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "briefing not found")
    try:
        req, code = await sign_briefing(
            session, tenant_id=str(tenant.id), briefing_id=briefing_id,
            person_id=payload.person_id, mode=payload.mode,
            requested_by=access.user.id if access else "system",
        )
    except (PepNotFound, PepConflict) as exc:
        raise _pep_to_http(exc) from exc
    return _signature_read(req, "briefing", confirm_code=code)


@router.get("/{wp_id}/signatures", response_model=list[WorkPermitSignatureRead])
async def list_signatures_endpoint(
    wp_id: str, tenant: TenantDep, session: SessionDep, access: ReaderAccess
) -> list[WorkPermitSignatureRead]:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _get_or_404(session, tenant, wp_id)
    permit_rows = (await session.execute(
        select(SignatureRequest).where(
            SignatureRequest.tenant_id == tenant.id,
            SignatureRequest.signature_type == "pep",
            SignatureRequest.object_type == "work_permit",
            SignatureRequest.object_id == wp_id,
        ).order_by(SignatureRequest.created_at.asc())
    )).scalars().all()
    briefings = await list_briefings(session, tenant_id=tenant.id, work_permit_id=wp_id)
    briefing_ids = [b.id for b in briefings]
    briefing_rows: list[SignatureRequest] = []
    if briefing_ids:
        briefing_rows = list((await session.execute(
            select(SignatureRequest).where(
                SignatureRequest.tenant_id == tenant.id,
                SignatureRequest.signature_type == "pep",
                SignatureRequest.object_type == "work_permit_briefing",
                SignatureRequest.object_id.in_(briefing_ids),
            ).order_by(SignatureRequest.created_at.asc())
        )).scalars().all())
    return (
        [_signature_read(r, "permit") for r in permit_rows]
        + [_signature_read(r, "briefing") for r in briefing_rows]
    )


# --- Closing endpoints (Ф3b) -----------------------------------------------

@router.post("/{wp_id}/closing", response_model=WorkPermitClosingSummary)
@audit_operation("update", "work_permit")
async def record_closing_endpoint(
    wp_id: str, payload: WorkPermitClosingRecordCreate, tenant: TenantDep,
    session: SessionDep, access: WriterAccess,
) -> WorkPermitClosingSummary:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _get_or_404(session, tenant, wp_id)
    try:
        wp = await record_completion(
            session, tenant_id=str(tenant.id), work_permit_id=wp_id,
            completion_text=payload.completion_text,
            actor_user_id=access.user.id if access else None,
        )
    except lc.WorkPermitTransitionError as exc:
        raise _transition_conflict(exc) from exc
    except lc.WorkPermitCompletionLocked as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=api_problem_detail(
                code="WORK_PERMIT_COMPLETION_LOCKED",
                message="completion act is locked by closing signatures",
                error_type="work_permit",
            ),
        ) from exc
    if wp is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "work permit not found")
    return await _closing_summary(session, tenant, wp)


@router.get("/{wp_id}/closing", response_model=WorkPermitClosingSummary)
async def get_closing_endpoint(
    wp_id: str, tenant: TenantDep, session: SessionDep, access: ReaderAccess,
) -> WorkPermitClosingSummary:
    TenantContextValidator.ensure_tenant_context(tenant)
    wp = await _get_or_404(session, tenant, wp_id)
    return await _closing_summary(session, tenant, wp)


@router.post(
    "/{wp_id}/closing/signatures",
    response_model=WorkPermitSignatureRead, status_code=status.HTTP_201_CREATED,
)
@audit_operation("update", "work_permit")
async def create_closing_signature_endpoint(
    wp_id: str, payload: WorkPermitSignatureCreate, tenant: TenantDep,
    session: SessionDep, access: WriterAccess,
) -> WorkPermitSignatureRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    wp = await _get_or_404(session, tenant, wp_id)
    if wp.status not in (lc.STATUS_ISSUED, lc.STATUS_SUSPENDED):
        raise _transition_conflict(lc.WorkPermitTransitionError(str(wp.status), "sign_closing"))
    await _ensure_person(session, tenant, payload.person_id)
    try:
        req, code = await sign_closing(
            session, tenant_id=str(tenant.id), work_permit_id=wp_id,
            person_id=payload.person_id, mode=payload.mode,
            requested_by=access.user.id if access else "system",
        )
    except (PepNotFound, PepConflict) as exc:
        raise _pep_to_http(exc) from exc
    return _signature_read(req, "closing", confirm_code=code)


# --- Print endpoint (Ф4) -----------------------------------------------------

@router.get("/{wp_id}/print")
async def print_work_permit_endpoint(
    wp_id: str, tenant: TenantDep, session: SessionDep, access: ReaderAccess,
    fmt: Literal["docx", "pdf"] = Query("docx", alias="format"),
) -> Response:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _get_or_404(session, tenant, wp_id)
    try:
        rendered = await render_work_permit(
            session, tenant=tenant, permit_id=wp_id, fmt=fmt,
        )
    except PdfRendererUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=api_problem_detail(
                code="PDF_RENDERER_UNAVAILABLE",
                message="PDF converter is unavailable",
                error_type="work_permit",
            ),
        ) from exc
    # defensive: _get_or_404 уже отсёк отсутствующий наряд; None здесь — параллельное удаление
    if rendered is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "work permit not found")
    encoded_name = quote(rendered.filename, safe="")
    content_disposition = f"attachment; filename*=UTF-8''{encoded_name}"
    return Response(
        content=rendered.content,
        media_type=rendered.media_type,
        headers={"Content-Disposition": content_disposition},
    )
