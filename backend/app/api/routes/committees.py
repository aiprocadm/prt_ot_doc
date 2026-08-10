"""Endpoints for committees / commissions / meetings (P10-01 срез-1/срез-2, TZ B.17)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.api.helpers.etag import (
    apply_etag_response_headers,
    build_not_modified_headers,
    compute_list_etag,
)
from app.core.errors import api_problem_detail
from app.core.feature_flags import is_module_enabled
from app.core.security import AccessContext, abac
from app.core.tenant_validation import TenantContextValidator
from app.domains.committees.kpi import CommitteeKpiService
from app.domains.committees.lifecycle import (
    MeetingTransitionError,
    ensure_can_invite,
    ensure_can_vote,
    ensure_meeting_held,
    is_quorum,
    next_protocol_seq,
    validate_meeting_transition,
)
from app.domains.committees.service import build_protocol, task_to_read, vote_summary
from app.models.committees import (
    Committee,
    CommitteeAgendaItem,
    CommitteeDecision,
    CommitteeDecisionTask,
    CommitteeDecisionVote,
    CommitteeMeeting,
    CommitteeMeetingAttendance,
    CommitteeMeetingInvitation,
    CommitteeMember,
    MeetingStatus,
)
from app.models.master_data import Person
from app.models.tenanting import Tenant
from app.schemas.committees import (
    AgendaItemCreate,
    AgendaItemRead,
    AttendanceBulkUpdate,
    AttendanceRead,
    CommitteeCreate,
    CommitteeKpiDto,
    CommitteePage,
    CommitteeRead,
    CommitteeUpdate,
    DecisionCreate,
    DecisionRead,
    DecisionTaskCreate,
    DecisionTaskRead,
    DecisionTaskUpdate,
    DecisionVoteSummary,
    InvitationBulkUpdate,
    InvitationRead,
    MeetingCreate,
    MeetingPage,
    MeetingRead,
    MeetingStatusUpdate,
    MemberCreate,
    MemberDetailRead,
    MemberRead,
    ProtocolJournalItem,
    ProtocolJournalPage,
    ProtocolRead,
    VoteCreate,
    VoteRead,
)
from app.services.committee_protocol_print import (
    PdfRendererUnavailable,
    render_committee_protocol,
)

router = APIRouter(prefix="/committees", tags=["committees"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[Tenant, Depends(get_tenant_record)]


def _tenant_resource_id(tenant: Tenant = Depends(get_tenant_record)) -> str | None:
    return getattr(tenant, "id", None)


_ROLES = ["admin"]
Access = Annotated[AccessContext, Depends(abac(_tenant_resource_id, required_roles=_ROLES))]

# KPI dashboard audience = management (mirrors analytics ``_ANALYTICS_READ_ROLES``),
# deliberately broader than the admin-only committee CRUD guard above so heads /
# managers can read execution KPIs without the committees-write role.
_KPI_ROLES = ["admin", "owner", "hr", "ot_pb_lead", "line_manager", "ot_specialist", "manager"]
KpiAccess = Annotated[AccessContext, Depends(abac(_tenant_resource_id, required_roles=_KPI_ROLES))]


_FEATURE_CODE = "committees"


def _feature_off() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=api_problem_detail(
            code="COMMITTEES_DISABLED",
            message="Committees module is not enabled for this tenant",
            error_type="committees",
        ),
    )


async def _require_committees_enabled(session: AsyncSession, tenant: Tenant) -> None:
    enabled = await is_module_enabled(session, str(tenant.id), _FEATURE_CODE)
    if not enabled:
        raise _feature_off()


def _conflict(exc: MeetingTransitionError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=api_problem_detail(
            code="COMMITTEE_TRANSITION_INVALID", message=str(exc), error_type="committees"
        ),
    )


def _not_found(what: str) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, f"{what} not found")


def _err(code: str, message: str, status_code: int) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail=api_problem_detail(code=code, message=message, error_type="committees"),
    )


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


# --- proceedings query helpers (patched in tests → module-level functions) ---
async def _count_members(session: AsyncSession, tenant: Tenant, committee_id: str) -> int:
    return int(
        (
            await session.execute(
                select(func.count(func.distinct(CommitteeMember.person_id))).where(
                    CommitteeMember.committee_id == committee_id,
                    CommitteeMember.tenant_id == tenant.id,
                )
            )
        ).scalar_one()
        or 0
    )


async def _count_present(session: AsyncSession, tenant: Tenant, meeting_id: str) -> int:
    return int(
        (
            await session.execute(
                select(func.count()).where(
                    CommitteeMeetingAttendance.meeting_id == meeting_id,
                    CommitteeMeetingAttendance.tenant_id == tenant.id,
                    CommitteeMeetingAttendance.present.is_(True),
                )
            )
        ).scalar_one()
        or 0
    )


async def _is_present(
    session: AsyncSession, tenant: Tenant, meeting_id: str, person_id: str
) -> bool:
    row = (
        await session.execute(
            select(CommitteeMeetingAttendance.id).where(
                CommitteeMeetingAttendance.meeting_id == meeting_id,
                CommitteeMeetingAttendance.tenant_id == tenant.id,
                CommitteeMeetingAttendance.person_id == person_id,
                CommitteeMeetingAttendance.present.is_(True),
            )
        )
    ).scalar_one_or_none()
    return row is not None


async def _committee_member_person_ids(
    session: AsyncSession, tenant: Tenant, committee_id: str
) -> set[str]:
    rows = (
        (
            await session.execute(
                select(CommitteeMember.person_id).where(
                    CommitteeMember.committee_id == committee_id,
                    CommitteeMember.tenant_id == tenant.id,
                )
            )
        )
        .scalars()
        .all()
    )
    return set(rows)


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
    await _require_committees_enabled(session, tenant)
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
        return Response(
            status_code=status.HTTP_304_NOT_MODIFIED, headers=build_not_modified_headers(etag)
        )
    return CommitteePage(
        items=[CommitteeRead.model_validate(c, from_attributes=True) for c in items],
        total=int(total or 0),
        limit=limit,
        offset=offset,
    )


# NOTE: /protocols MUST be declared before GET /{cid} — FastAPI matches by
# declaration order; otherwise GET /committees/protocols binds cid="protocols".
@router.get("/protocols", response_model=ProtocolJournalPage)
async def list_protocols(
    request: Request,
    response: Response,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
    committee_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> ProtocolJournalPage | Response:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _require_committees_enabled(session, tenant)
    conds = [
        CommitteeMeeting.tenant_id == tenant.id,
        CommitteeMeeting.deleted_at.is_(None),
        CommitteeMeeting.protocol_seq.is_not(None),
    ]
    if committee_id:
        conds.append(CommitteeMeeting.committee_id == committee_id)
    stmt = (
        select(CommitteeMeeting, Committee.name)
        .join(Committee, Committee.id == CommitteeMeeting.committee_id)
        .where(*conds)
        .order_by(
            CommitteeMeeting.protocol_year.desc(),
            CommitteeMeeting.protocol_seq.desc(),
        )
        .limit(limit)
        .offset(offset)
    )
    rows = list((await session.execute(stmt)).all())
    total = (await session.execute(select(func.count()).where(*conds))).scalar_one()
    # decisions_count per meeting (single grouped query)
    meeting_ids = [m.id for m, _ in rows]
    counts: dict[str, int] = {}
    if meeting_ids:
        for mid_, cnt in (
            await session.execute(
                select(CommitteeDecision.meeting_id, func.count())
                .where(
                    CommitteeDecision.meeting_id.in_(meeting_ids),
                    CommitteeDecision.tenant_id == tenant.id,
                )
                .group_by(CommitteeDecision.meeting_id)
            )
        ).all():
            counts[mid_] = cnt
    items = [
        ProtocolJournalItem(
            meeting_id=m.id,
            committee_id=m.committee_id,
            committee_name=name,
            protocol_no=f"{m.protocol_seq}/{m.protocol_year}",
            held_at=m.held_at,
            members_total=m.members_total,
            present_count=m.present_count,
            decisions_count=counts.get(m.id, 0),
        )
        for m, name in rows
    ]
    etag = compute_list_etag(
        tenant_id=str(tenant.id),
        items=[m for m, _ in rows],
        scalars=[
            ("total", int(total or 0)),
            ("limit", limit),
            ("offset", offset),
            ("cid", committee_id or ""),
        ],
    )
    apply_etag_response_headers(response, etag)
    if request.headers.get("if-none-match") == etag:
        return Response(
            status_code=status.HTTP_304_NOT_MODIFIED, headers=build_not_modified_headers(etag)
        )
    return ProtocolJournalPage(items=items, total=int(total or 0), limit=limit, offset=offset)


# NOTE: /kpi (like /protocols) MUST be declared before GET /{cid}, otherwise
# FastAPI binds cid="kpi". Audience is management (KpiAccess), not admin-only.
@router.get("/kpi", response_model=CommitteeKpiDto)
async def committee_kpi(
    request: Request,
    response: Response,
    tenant: TenantDep,
    session: SessionDep,
    access: KpiAccess,
    committee_id: str | None = Query(None),
) -> CommitteeKpiDto | Response:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _require_committees_enabled(session, tenant)
    kpi = await CommitteeKpiService(session, str(tenant.id)).compute(committee_id=committee_id)
    etag = compute_list_etag(
        tenant_id=str(tenant.id),
        items=[],
        scalars=[("cid", committee_id or ""), *kpi.model_dump().items()],
    )
    apply_etag_response_headers(response, etag)
    if request.headers.get("if-none-match") == etag:
        return Response(
            status_code=status.HTTP_304_NOT_MODIFIED, headers=build_not_modified_headers(etag)
        )
    return kpi


@router.post("", response_model=CommitteeRead, status_code=status.HTTP_201_CREATED)
async def create_committee(
    payload: CommitteeCreate, tenant: TenantDep, session: SessionDep, access: Access
) -> CommitteeRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _require_committees_enabled(session, tenant)
    row = Committee(
        tenant_id=tenant.id,
        kind=payload.kind,
        name=payload.name,
        description=payload.description,
        is_active=payload.is_active,
        quorum_threshold_pct=payload.quorum_threshold_pct,
    )
    session.add(row)
    await session.flush()
    await session.refresh(row)
    return CommitteeRead.model_validate(row, from_attributes=True)


@router.get("/{cid}", response_model=CommitteeRead)
async def get_committee(
    cid: str, tenant: TenantDep, session: SessionDep, access: Access
) -> CommitteeRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _require_committees_enabled(session, tenant)
    row = await _get_committee(session, tenant, cid)
    return CommitteeRead.model_validate(row, from_attributes=True)


@router.patch("/{cid}", response_model=CommitteeRead)
async def update_committee(
    cid: str, payload: CommitteeUpdate, tenant: TenantDep, session: SessionDep, access: Access
) -> CommitteeRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _require_committees_enabled(session, tenant)
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
    await _require_committees_enabled(session, tenant)
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
    await _require_committees_enabled(session, tenant)
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


@router.get("/{cid}/members", response_model=list[MemberDetailRead])
async def list_members(
    cid: str, tenant: TenantDep, session: SessionDep, access: Access
) -> list[MemberDetailRead]:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _require_committees_enabled(session, tenant)
    await _get_committee(session, tenant, cid)
    rows = (
        await session.execute(
            select(CommitteeMember, Person)
            .join(Person, Person.id == CommitteeMember.person_id)
            .where(
                CommitteeMember.committee_id == cid,
                CommitteeMember.tenant_id == tenant.id,
            )
            .order_by(CommitteeMember.role.asc())
        )
    ).all()
    result = []
    for m, pers in rows:
        fio = (
            " ".join(
                p
                for p in [
                    getattr(pers, "last_name", None),
                    getattr(pers, "first_name", None),
                    getattr(pers, "middle_name", None),
                ]
                if p
            )
            or None
        )
        result.append(
            MemberDetailRead(
                id=m.id,
                committee_id=m.committee_id,
                person_id=m.person_id,
                role=m.role,
                person_fio=fio,
            )
        )
    return result


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
    await _require_committees_enabled(session, tenant)
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
        return Response(
            status_code=status.HTTP_304_NOT_MODIFIED, headers=build_not_modified_headers(etag)
        )
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
    await _require_committees_enabled(session, tenant)
    await _get_committee(session, tenant, cid)
    row = CommitteeMeeting(
        tenant_id=tenant.id,
        committee_id=cid,
        scheduled_at=payload.scheduled_at,
        location=payload.location,
    )
    session.add(row)
    await session.flush()
    await session.refresh(row)
    return MeetingRead.model_validate(row, from_attributes=True)


@router.get("/meetings/{mid}", response_model=MeetingRead)
async def get_meeting(
    mid: str, tenant: TenantDep, session: SessionDep, access: Access
) -> MeetingRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _require_committees_enabled(session, tenant)
    row = await _get_meeting(session, tenant, mid)
    return MeetingRead.model_validate(row, from_attributes=True)


@router.patch("/meetings/{mid}", response_model=MeetingRead)
async def update_meeting(
    mid: str, payload: MeetingStatusUpdate, tenant: TenantDep, session: SessionDep, access: Access
) -> MeetingRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _require_committees_enabled(session, tenant)
    row = await _get_meeting(session, tenant, mid)
    if payload.status is MeetingStatus.HELD:
        try:
            validate_meeting_transition(row.status, MeetingStatus.HELD)
        except MeetingTransitionError as exc:
            raise _conflict(exc)
        committee = await _get_committee(session, tenant, row.committee_id)
        members_total = await _count_members(session, tenant, row.committee_id)
        present_count = await _count_present(session, tenant, mid)
        if not is_quorum(
            members_total, present_count, threshold_pct=committee.quorum_threshold_pct
        ):
            raise _err(
                "COMMITTEE_QUORUM_NOT_MET",
                "Quorum not met",
                status.HTTP_409_CONFLICT,
            )
        now = datetime.now(tz=timezone.utc)
        year = now.year
        seqs = (
            (
                await session.execute(
                    select(CommitteeMeeting.protocol_seq).where(
                        CommitteeMeeting.committee_id == row.committee_id,
                        CommitteeMeeting.tenant_id == tenant.id,
                        CommitteeMeeting.protocol_year == year,
                        CommitteeMeeting.protocol_seq.is_not(None),
                    )
                )
            )
            .scalars()
            .all()
        )
        row.protocol_seq = next_protocol_seq([s for s in seqs if s is not None])
        row.protocol_year = year
        row.held_at = now
        row.members_total = members_total
        row.present_count = present_count
        row.quorum_met = True
        row.status = MeetingStatus.HELD
        try:
            await session.flush()
        except IntegrityError:
            await session.rollback()
            raise _err(
                "COMMITTEE_PROTOCOL_CONFLICT",
                "Protocol number conflict, retry",
                status.HTTP_409_CONFLICT,
            )
        await session.refresh(row)
        return MeetingRead.model_validate(row, from_attributes=True)
    try:
        validate_meeting_transition(row.status, payload.status)
    except MeetingTransitionError as exc:
        raise _conflict(exc)
    row.status = payload.status
    await session.flush()
    await session.refresh(row)
    return MeetingRead.model_validate(row, from_attributes=True)


# --- Attendance ---
@router.get("/meetings/{mid}/attendance", response_model=list[AttendanceRead])
async def get_attendance(
    mid: str, tenant: TenantDep, session: SessionDep, access: Access
) -> list[AttendanceRead]:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _require_committees_enabled(session, tenant)
    await _get_meeting(session, tenant, mid)
    rows = (
        (
            await session.execute(
                select(CommitteeMeetingAttendance).where(
                    CommitteeMeetingAttendance.meeting_id == mid,
                    CommitteeMeetingAttendance.tenant_id == tenant.id,
                )
            )
        )
        .scalars()
        .all()
    )
    return [AttendanceRead.model_validate(r, from_attributes=True) for r in rows]


@router.put("/meetings/{mid}/attendance", response_model=list[AttendanceRead])
async def put_attendance(
    mid: str,
    payload: AttendanceBulkUpdate,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
) -> list[AttendanceRead]:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _require_committees_enabled(session, tenant)
    meeting = await _get_meeting(session, tenant, mid)
    if meeting.status is not MeetingStatus.PLANNED:
        raise _err(
            "COMMITTEE_MEETING_NOT_PLANNED",
            "Attendance editable only before the meeting is held",
            status.HTTP_409_CONFLICT,
        )
    # Dedupe by person_id (last-write-wins, insertion-ordered) so a person_id
    # repeated in the payload collapses to a single attendance row instead of
    # inserting twice → violating uq_committee_attendance → IntegrityError → 500.
    desired: dict[str, bool] = {}
    for item in payload.items:
        desired[item.person_id] = item.present
    member_ids = await _committee_member_person_ids(session, tenant, meeting.committee_id)
    for person_id in desired:
        if person_id not in member_ids:
            raise _err(
                "COMMITTEE_NOT_A_MEMBER",
                f"person {person_id} is not a committee member",
                status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
    existing = (
        (
            await session.execute(
                select(CommitteeMeetingAttendance).where(
                    CommitteeMeetingAttendance.meeting_id == mid,
                    CommitteeMeetingAttendance.tenant_id == tenant.id,
                )
            )
        )
        .scalars()
        .all()
    )
    by_person = {r.person_id: r for r in existing}
    for person_id, present in desired.items():
        row = by_person.get(person_id)
        if row is None:
            row = CommitteeMeetingAttendance(
                tenant_id=tenant.id,
                meeting_id=mid,
                person_id=person_id,
                present=present,
            )
            session.add(row)
        else:
            row.present = present
    await session.flush()
    return await get_attendance(mid=mid, tenant=tenant, session=session, access=access)


# --- Invitations (срез-4) ---
@router.get("/meetings/{mid}/invitations", response_model=list[InvitationRead])
async def get_invitations(
    mid: str, tenant: TenantDep, session: SessionDep, access: Access
) -> list[InvitationRead]:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _require_committees_enabled(session, tenant)
    await _get_meeting(session, tenant, mid)
    rows = (
        (
            await session.execute(
                select(CommitteeMeetingInvitation).where(
                    CommitteeMeetingInvitation.meeting_id == mid,
                    CommitteeMeetingInvitation.tenant_id == tenant.id,
                )
            )
        )
        .scalars()
        .all()
    )
    return [InvitationRead.model_validate(r, from_attributes=True) for r in rows]


@router.put("/meetings/{mid}/invitations", response_model=list[InvitationRead])
async def put_invitations(
    mid: str,
    payload: InvitationBulkUpdate,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
) -> list[InvitationRead]:
    """Заменить набор приглашённых (PUT-семантика, как у attendance).

    В отличие от присутствия, приглашения НЕ ограничены членами комитета:
    на заседание зовут и внешних участников (эксперт, докладчик).
    """
    TenantContextValidator.ensure_tenant_context(tenant)
    await _require_committees_enabled(session, tenant)
    meeting = await _get_meeting(session, tenant, mid)
    try:
        ensure_can_invite(meeting.status)
    except MeetingTransitionError as exc:
        raise _conflict(exc)
    # Дедуп payload (повтор person_id → одна строка, не IntegrityError).
    desired = list(dict.fromkeys(payload.person_ids))
    existing = (
        (
            await session.execute(
                select(CommitteeMeetingInvitation).where(
                    CommitteeMeetingInvitation.meeting_id == mid,
                    CommitteeMeetingInvitation.tenant_id == tenant.id,
                )
            )
        )
        .scalars()
        .all()
    )
    by_person = {r.person_id: r for r in existing}
    for person_id in desired:
        if person_id not in by_person:
            session.add(
                CommitteeMeetingInvitation(
                    tenant_id=tenant.id,
                    meeting_id=mid,
                    person_id=person_id,
                    invited_at=datetime.now(tz=timezone.utc),
                )
            )
    for person_id, row in by_person.items():
        if person_id not in desired:
            await session.delete(row)
    await session.flush()
    return await get_invitations(mid=mid, tenant=tenant, session=session, access=access)


@router.post(
    "/meetings/{mid}/agenda-items",
    response_model=AgendaItemRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_agenda_item(
    mid: str, payload: AgendaItemCreate, tenant: TenantDep, session: SessionDep, access: Access
) -> AgendaItemRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _require_committees_enabled(session, tenant)
    await _get_meeting(session, tenant, mid)
    row = CommitteeAgendaItem(
        tenant_id=tenant.id,
        meeting_id=mid,
        seq=payload.seq,
        title=payload.title,
        presenter_person_id=payload.presenter_person_id,
    )
    session.add(row)
    await session.flush()
    await session.refresh(row)
    return AgendaItemRead.model_validate(row, from_attributes=True)


# --- Decisions ---
@router.post(
    "/meetings/{mid}/decisions", response_model=DecisionRead, status_code=status.HTTP_201_CREATED
)
async def create_decision(
    mid: str, payload: DecisionCreate, tenant: TenantDep, session: SessionDep, access: Access
) -> DecisionRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _require_committees_enabled(session, tenant)
    meeting = await _get_meeting(session, tenant, mid)
    try:
        ensure_meeting_held(meeting.status)
    except MeetingTransitionError as exc:
        raise _conflict(exc)
    row = CommitteeDecision(
        tenant_id=tenant.id,
        meeting_id=mid,
        agenda_item_id=payload.agenda_item_id,
        text=payload.text,
    )
    session.add(row)
    await session.flush()
    await session.refresh(row)
    return DecisionRead.model_validate(row, from_attributes=True)


@router.get("/meetings/{mid}/protocol/print")
async def print_protocol(
    mid: str,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
    fmt: Literal["docx", "pdf"] = Query("docx", alias="format"),
) -> Response:
    """Печатная форма протокола (срез-4). Только для проведённого заседания."""
    TenantContextValidator.ensure_tenant_context(tenant)
    await _require_committees_enabled(session, tenant)
    meeting = await _get_meeting(session, tenant, mid)
    try:
        ensure_meeting_held(meeting.status)
    except MeetingTransitionError as exc:
        raise _conflict(exc)
    try:
        rendered = await render_committee_protocol(
            session, tenant_id=tenant.id, meeting=meeting, fmt=fmt
        )
    except PdfRendererUnavailable:
        raise _err(
            "PDF_RENDERER_UNAVAILABLE",
            "PDF converter is unavailable",
            status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    encoded_name = quote(rendered.filename, safe="")
    return Response(
        content=rendered.content,
        media_type=rendered.media_type,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_name}"},
    )


@router.get("/meetings/{mid}/protocol", response_model=ProtocolRead)
async def get_protocol(
    mid: str, tenant: TenantDep, session: SessionDep, access: Access
) -> ProtocolRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _require_committees_enabled(session, tenant)
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
        )
        .scalars()
        .all()
    )
    triples = []
    for d in decisions:
        tasks = list(
            (
                await session.execute(
                    select(CommitteeDecisionTask).where(
                        CommitteeDecisionTask.decision_id == d.id,
                        CommitteeDecisionTask.tenant_id == tenant.id,
                    )
                )
            )
            .scalars()
            .all()
        )
        votes = list(
            (
                await session.execute(
                    select(CommitteeDecisionVote).where(
                        CommitteeDecisionVote.decision_id == d.id,
                        CommitteeDecisionVote.tenant_id == tenant.id,
                    )
                )
            )
            .scalars()
            .all()
        )
        triples.append((d, tasks, votes))
    return build_protocol(meeting, triples)


@router.post(
    "/decisions/{did}/tasks", response_model=DecisionTaskRead, status_code=status.HTTP_201_CREATED
)
async def create_task(
    did: str, payload: DecisionTaskCreate, tenant: TenantDep, session: SessionDep, access: Access
) -> DecisionTaskRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _require_committees_enabled(session, tenant)
    await _get_decision(session, tenant, did)
    row = CommitteeDecisionTask(
        tenant_id=tenant.id,
        decision_id=did,
        assignee_person_id=payload.assignee_person_id,
        due_date=payload.due_date,
        evidence_note=payload.evidence_note,
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
    await _require_committees_enabled(session, tenant)
    row = await _get_task(session, tenant, tid)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    await session.flush()
    await session.refresh(row)
    return task_to_read(row)


# --- Votes ---
@router.post("/decisions/{did}/votes", response_model=VoteRead, status_code=status.HTTP_201_CREATED)
async def cast_vote(
    did: str, payload: VoteCreate, tenant: TenantDep, session: SessionDep, access: Access
) -> VoteRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _require_committees_enabled(session, tenant)
    decision = await _get_decision(session, tenant, did)
    meeting = await _get_meeting(session, tenant, decision.meeting_id)
    try:
        ensure_can_vote(meeting.status)
    except MeetingTransitionError as exc:
        raise _err("COMMITTEE_DECISION_NOT_HELD", str(exc), status.HTTP_409_CONFLICT)
    if not await _is_present(session, tenant, decision.meeting_id, payload.person_id):
        raise _err(
            "COMMITTEE_VOTER_ABSENT",
            "Voter not present at meeting",
            status.HTTP_409_CONFLICT,
        )
    existing = (
        await session.execute(
            select(CommitteeDecisionVote).where(
                CommitteeDecisionVote.decision_id == did,
                CommitteeDecisionVote.tenant_id == tenant.id,
                CommitteeDecisionVote.person_id == payload.person_id,
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        existing = CommitteeDecisionVote(
            tenant_id=tenant.id,
            decision_id=did,
            person_id=payload.person_id,
            choice=payload.choice,
        )
        session.add(existing)
    else:
        existing.choice = payload.choice
    await session.flush()
    await session.refresh(existing)
    return VoteRead.model_validate(existing, from_attributes=True)


@router.get("/decisions/{did}/votes", response_model=DecisionVoteSummary)
async def get_votes(
    did: str, tenant: TenantDep, session: SessionDep, access: Access
) -> DecisionVoteSummary:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _require_committees_enabled(session, tenant)
    await _get_decision(session, tenant, did)
    votes = (
        (
            await session.execute(
                select(CommitteeDecisionVote).where(
                    CommitteeDecisionVote.decision_id == did,
                    CommitteeDecisionVote.tenant_id == tenant.id,
                )
            )
        )
        .scalars()
        .all()
    )
    return vote_summary(did, votes)
