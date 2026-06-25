"""Endpoints for committees / commissions / meetings (P10-01 срез-1, TZ B.17)."""
from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.api.helpers.etag import (
    apply_etag_response_headers,
    build_not_modified_headers,
    compute_list_etag,
)
from app.core.errors import api_problem_detail
from app.core.security import AccessContext, abac
from app.core.tenant_validation import TenantContextValidator
from app.domains.committees.lifecycle import (
    MeetingTransitionError,
    ensure_meeting_held,
    validate_meeting_transition,
)
from app.domains.committees.service import build_protocol, task_to_read
from app.models.committees import (
    Committee,
    CommitteeAgendaItem,
    CommitteeDecision,
    CommitteeDecisionTask,
    CommitteeMeeting,
    CommitteeMember,
)
from app.models.tenanting import Tenant
from app.schemas.committees import (
    AgendaItemCreate,
    AgendaItemRead,
    CommitteeCreate,
    CommitteePage,
    CommitteeRead,
    CommitteeUpdate,
    DecisionCreate,
    DecisionRead,
    DecisionTaskCreate,
    DecisionTaskRead,
    DecisionTaskUpdate,
    MeetingCreate,
    MeetingPage,
    MeetingRead,
    MeetingStatusUpdate,
    MemberCreate,
    MemberRead,
    ProtocolRead,
)

router = APIRouter(prefix="/committees", tags=["committees"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[Tenant, Depends(get_tenant_record)]


def _tenant_resource_id(tenant: Tenant = Depends(get_tenant_record)) -> str | None:
    return getattr(tenant, "id", None)


_ROLES = ["admin"]
Access = Annotated[AccessContext, Depends(abac(_tenant_resource_id, required_roles=_ROLES))]


def _conflict(exc: MeetingTransitionError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=api_problem_detail(
            code="COMMITTEE_TRANSITION_INVALID", message=str(exc), error_type="committees"
        ),
    )


def _not_found(what: str) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, f"{what} not found")


# --- tenant-scoped getters (patched in tests) ---
async def _get_committee(session: AsyncSession, tenant: Tenant, cid: str) -> Committee:
    row = (
        await session.execute(
            select(Committee).where(
                Committee.id == cid,
                Committee.tenant_id == tenant.id,
                Committee.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise _not_found("Committee")
    return row


async def _get_meeting(session: AsyncSession, tenant: Tenant, mid: str) -> CommitteeMeeting:
    row = (
        await session.execute(
            select(CommitteeMeeting).where(
                CommitteeMeeting.id == mid,
                CommitteeMeeting.tenant_id == tenant.id,
                CommitteeMeeting.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise _not_found("Meeting")
    return row


async def _get_decision(session: AsyncSession, tenant: Tenant, did: str) -> CommitteeDecision:
    row = (
        await session.execute(
            select(CommitteeDecision).where(
                CommitteeDecision.id == did, CommitteeDecision.tenant_id == tenant.id
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise _not_found("Decision")
    return row


async def _get_task(session: AsyncSession, tenant: Tenant, tid: str) -> CommitteeDecisionTask:
    row = (
        await session.execute(
            select(CommitteeDecisionTask).where(
                CommitteeDecisionTask.id == tid,
                CommitteeDecisionTask.tenant_id == tenant.id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise _not_found("Task")
    return row


# --- Committees ---
@router.get("", response_model=CommitteePage)
async def list_committees(
    request: Request,
    response: Response,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> CommitteePage | Response:
    TenantContextValidator.ensure_tenant_context(tenant)
    stmt = (
        select(Committee)
        .where(Committee.tenant_id == tenant.id, Committee.deleted_at.is_(None))
        .order_by(Committee.name.asc())
        .limit(limit)
        .offset(offset)
    )
    items = list((await session.execute(stmt)).scalars().all())
    total = (
        await session.execute(
            select(func.count()).where(
                Committee.tenant_id == tenant.id, Committee.deleted_at.is_(None)
            )
        )
    ).scalar_one()
    etag = compute_list_etag(
        tenant_id=str(tenant.id),
        items=items,
        scalars=[("total", int(total or 0)), ("limit", limit), ("offset", offset)],
    )
    apply_etag_response_headers(response, etag)
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=build_not_modified_headers(etag))
    return CommitteePage(
        items=[CommitteeRead.model_validate(c, from_attributes=True) for c in items],
        total=int(total or 0),
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=CommitteeRead, status_code=status.HTTP_201_CREATED)
async def create_committee(
    payload: CommitteeCreate, tenant: TenantDep, session: SessionDep, access: Access
) -> CommitteeRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    row = Committee(
        tenant_id=tenant.id,
        kind=payload.kind,
        name=payload.name,
        description=payload.description,
        is_active=payload.is_active,
    )
    session.add(row)
    await session.flush()
    await session.refresh(row)
    return CommitteeRead.model_validate(row, from_attributes=True)


@router.get("/{cid}", response_model=CommitteeRead)
async def get_committee(cid: str, tenant: TenantDep, session: SessionDep, access: Access) -> CommitteeRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    row = await _get_committee(session, tenant, cid)
    return CommitteeRead.model_validate(row, from_attributes=True)


@router.patch("/{cid}", response_model=CommitteeRead)
async def update_committee(
    cid: str, payload: CommitteeUpdate, tenant: TenantDep, session: SessionDep, access: Access
) -> CommitteeRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    row = await _get_committee(session, tenant, cid)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    await session.flush()
    await session.refresh(row)
    return CommitteeRead.model_validate(row, from_attributes=True)


# --- Members ---
@router.post("/{cid}/members", response_model=MemberRead, status_code=status.HTTP_201_CREATED)
async def add_member(
    cid: str, payload: MemberCreate, tenant: TenantDep, session: SessionDep, access: Access
) -> MemberRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _get_committee(session, tenant, cid)
    row = CommitteeMember(
        tenant_id=tenant.id, committee_id=cid, person_id=payload.person_id, role=payload.role
    )
    session.add(row)
    await session.flush()
    await session.refresh(row)
    return MemberRead.model_validate(row, from_attributes=True)


@router.delete("/{cid}/members/{mid}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    cid: str, mid: str, tenant: TenantDep, session: SessionDep, access: Access
) -> Response:
    TenantContextValidator.ensure_tenant_context(tenant)
    row = (
        await session.execute(
            select(CommitteeMember).where(
                CommitteeMember.id == mid,
                CommitteeMember.committee_id == cid,
                CommitteeMember.tenant_id == tenant.id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise _not_found("Member")
    await session.delete(row)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Meetings ---
@router.get("/{cid}/meetings", response_model=MeetingPage)
async def list_meetings(
    cid: str,
    request: Request,
    response: Response,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> MeetingPage | Response:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _get_committee(session, tenant, cid)
    stmt = (
        select(CommitteeMeeting)
        .where(
            CommitteeMeeting.committee_id == cid,
            CommitteeMeeting.tenant_id == tenant.id,
            CommitteeMeeting.deleted_at.is_(None),
        )
        .order_by(CommitteeMeeting.scheduled_at.desc())
        .limit(limit)
        .offset(offset)
    )
    items = list((await session.execute(stmt)).scalars().all())
    total = (
        await session.execute(
            select(func.count()).where(
                CommitteeMeeting.committee_id == cid,
                CommitteeMeeting.tenant_id == tenant.id,
                CommitteeMeeting.deleted_at.is_(None),
            )
        )
    ).scalar_one()
    etag = compute_list_etag(
        tenant_id=str(tenant.id),
        items=items,
        scalars=[("cid", cid), ("total", int(total or 0)), ("limit", limit), ("offset", offset)],
    )
    apply_etag_response_headers(response, etag)
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=build_not_modified_headers(etag))
    return MeetingPage(
        items=[MeetingRead.model_validate(m, from_attributes=True) for m in items],
        total=int(total or 0),
        limit=limit,
        offset=offset,
    )


@router.post("/{cid}/meetings", response_model=MeetingRead, status_code=status.HTTP_201_CREATED)
async def schedule_meeting(
    cid: str, payload: MeetingCreate, tenant: TenantDep, session: SessionDep, access: Access
) -> MeetingRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _get_committee(session, tenant, cid)
    row = CommitteeMeeting(
        tenant_id=tenant.id, committee_id=cid,
        scheduled_at=payload.scheduled_at, location=payload.location,
    )
    session.add(row)
    await session.flush()
    await session.refresh(row)
    return MeetingRead.model_validate(row, from_attributes=True)


@router.get("/meetings/{mid}", response_model=MeetingRead)
async def get_meeting(mid: str, tenant: TenantDep, session: SessionDep, access: Access) -> MeetingRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    row = await _get_meeting(session, tenant, mid)
    return MeetingRead.model_validate(row, from_attributes=True)


@router.patch("/meetings/{mid}", response_model=MeetingRead)
async def update_meeting(
    mid: str, payload: MeetingStatusUpdate, tenant: TenantDep, session: SessionDep, access: Access
) -> MeetingRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    row = await _get_meeting(session, tenant, mid)
    try:
        validate_meeting_transition(row.status, payload.status)
    except MeetingTransitionError as exc:
        raise _conflict(exc)
    row.status = payload.status
    await session.flush()
    await session.refresh(row)
    return MeetingRead.model_validate(row, from_attributes=True)


@router.post("/meetings/{mid}/agenda-items", response_model=AgendaItemRead, status_code=status.HTTP_201_CREATED)
async def create_agenda_item(
    mid: str, payload: AgendaItemCreate, tenant: TenantDep, session: SessionDep, access: Access
) -> AgendaItemRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _get_meeting(session, tenant, mid)
    row = CommitteeAgendaItem(
        tenant_id=tenant.id, meeting_id=mid,
        seq=payload.seq, title=payload.title, presenter_person_id=payload.presenter_person_id,
    )
    session.add(row)
    await session.flush()
    await session.refresh(row)
    return AgendaItemRead.model_validate(row, from_attributes=True)


# --- Decisions ---
@router.post("/meetings/{mid}/decisions", response_model=DecisionRead, status_code=status.HTTP_201_CREATED)
async def create_decision(
    mid: str, payload: DecisionCreate, tenant: TenantDep, session: SessionDep, access: Access
) -> DecisionRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    meeting = await _get_meeting(session, tenant, mid)
    try:
        ensure_meeting_held(meeting.status)
    except MeetingTransitionError as exc:
        raise _conflict(exc)
    row = CommitteeDecision(
        tenant_id=tenant.id, meeting_id=mid,
        agenda_item_id=payload.agenda_item_id, text=payload.text,
    )
    session.add(row)
    await session.flush()
    await session.refresh(row)
    return DecisionRead.model_validate(row, from_attributes=True)


@router.get("/meetings/{mid}/protocol", response_model=ProtocolRead)
async def get_protocol(
    mid: str, tenant: TenantDep, session: SessionDep, access: Access
) -> ProtocolRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    meeting = await _get_meeting(session, tenant, mid)
    decisions = list(
        (
            await session.execute(
                select(CommitteeDecision)
                .where(
                    CommitteeDecision.meeting_id == mid,
                    CommitteeDecision.tenant_id == tenant.id,
                )
                .order_by(CommitteeDecision.decided_at.asc())
            )
        ).scalars().all()
    )
    pairs = []
    for d in decisions:
        tasks = list(
            (
                await session.execute(
                    select(CommitteeDecisionTask).where(
                        CommitteeDecisionTask.decision_id == d.id,
                        CommitteeDecisionTask.tenant_id == tenant.id,
                    )
                )
            ).scalars().all()
        )
        pairs.append((d, tasks))
    return build_protocol(meeting, pairs)


@router.post("/decisions/{did}/tasks", response_model=DecisionTaskRead, status_code=status.HTTP_201_CREATED)
async def create_task(
    did: str, payload: DecisionTaskCreate, tenant: TenantDep, session: SessionDep, access: Access
) -> DecisionTaskRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _get_decision(session, tenant, did)
    row = CommitteeDecisionTask(
        tenant_id=tenant.id, decision_id=did,
        assignee_person_id=payload.assignee_person_id,
        due_date=payload.due_date, evidence_note=payload.evidence_note,
    )
    session.add(row)
    await session.flush()
    await session.refresh(row)
    return task_to_read(row)


@router.patch("/tasks/{tid}", response_model=DecisionTaskRead)
async def update_task(
    tid: str, payload: DecisionTaskUpdate, tenant: TenantDep, session: SessionDep, access: Access
) -> DecisionTaskRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    row = await _get_task(session, tenant, tid)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    await session.flush()
    await session.refresh(row)
    return task_to_read(row)
