"""Session-aware operations for work permits (наряды-допуски)."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.work_permits import lifecycle as lc
from app.models.work_permit import WorkPermit, WorkPermitBriefing, WorkPermitEvent, WorkPermitMember


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


async def _get(session: AsyncSession, tenant_id: str, work_permit_id: str) -> WorkPermit | None:
    stmt = select(WorkPermit).where(
        WorkPermit.id == work_permit_id, WorkPermit.tenant_id == tenant_id
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def _log(
    session: AsyncSession, *, tenant_id: str, work_permit_id: str, event_type: str,
    actor_user_id: str | None, photo_file_id: str | None = None, note: str | None = None,
) -> WorkPermitEvent:
    event = WorkPermitEvent(
        tenant_id=tenant_id, work_permit_id=work_permit_id, event_type=event_type,
        at=_now(), actor_user_id=actor_user_id, photo_file_id=photo_file_id, note=note,
    )
    session.add(event)
    await session.flush()
    return event


async def create_work_permit(
    session: AsyncSession, *, tenant_id: str, work_type: str, zone_text: str,
    number: str | None = None, site_id: str | None = None, equipment_text: str | None = None,
    hazards_text: str | None = None, measures_text: str | None = None,
    planned_start: datetime | None = None, planned_end: datetime | None = None,
    subdivision_text: str | None = None, content_text: str | None = None,
    conditions_text: str | None = None, safety_systems: list[str] | None = None,
    measures_before_text: str | None = None, measures_during_text: str | None = None,
    special_conditions_text: str | None = None, ppe_text: str | None = None,
) -> WorkPermit:
    wp = WorkPermit(
        tenant_id=tenant_id, work_type=work_type, zone_text=zone_text, number=number,
        site_id=site_id, equipment_text=equipment_text, hazards_text=hazards_text,
        measures_text=measures_text, planned_start=planned_start, planned_end=planned_end,
        subdivision_text=subdivision_text, content_text=content_text,
        conditions_text=conditions_text, safety_systems=safety_systems,
        measures_before_text=measures_before_text, measures_during_text=measures_during_text,
        special_conditions_text=special_conditions_text, ppe_text=ppe_text,
        status=lc.STATUS_DRAFT,
    )
    session.add(wp)
    await session.flush()
    await session.refresh(wp)
    return wp


_DRAFT_EDITABLE = ("number", "work_type", "zone_text", "site_id", "equipment_text",
                   "hazards_text", "measures_text", "planned_start", "planned_end",
                   "subdivision_text", "content_text", "conditions_text", "safety_systems",
                   "measures_before_text", "measures_during_text", "special_conditions_text",
                   "ppe_text")


async def update_work_permit(
    session: AsyncSession, *, tenant_id: str, work_permit_id: str, **fields,
) -> WorkPermit | None:
    """Edit a draft permit. None if not found; WorkPermitTransitionError if not draft.

    Only keys in ``fields`` that are present are applied (caller passes exactly the
    fields to change; pass None explicitly to clear a nullable column)."""
    wp = await _get(session, tenant_id, work_permit_id)
    if wp is None:
        return None
    if wp.status != lc.STATUS_DRAFT:
        raise lc.WorkPermitTransitionError(str(wp.status), "edit")
    for key, value in fields.items():
        if key in _DRAFT_EDITABLE:
            setattr(wp, key, value)
    await session.flush()
    await session.refresh(wp)
    return wp


async def delete_draft(session: AsyncSession, *, tenant_id: str, work_permit_id: str) -> bool:
    wp = await _get(session, tenant_id, work_permit_id)
    if wp is None:
        return False
    if wp.status != lc.STATUS_DRAFT:
        raise lc.WorkPermitTransitionError(str(wp.status), "delete")
    await session.delete(wp)
    await session.flush()
    return True


_TERMINAL = (lc.STATUS_CLOSED, lc.STATUS_CANCELLED)


async def add_member(
    session: AsyncSession, *, tenant_id: str, work_permit_id: str, person_id: str, role: str,
) -> WorkPermitMember | None:
    wp = await _get(session, tenant_id, work_permit_id)
    if wp is None:
        return None
    if wp.status in _TERMINAL:
        raise lc.WorkPermitTransitionError(str(wp.status), "add_member")
    member = WorkPermitMember(
        tenant_id=tenant_id, work_permit_id=work_permit_id, person_id=person_id, role=role,
    )
    session.add(member)
    await session.flush()
    await session.refresh(member)
    return member


async def remove_member(
    session: AsyncSession, *, tenant_id: str, work_permit_id: str, member_id: str,
) -> bool:
    stmt = select(WorkPermitMember).where(
        WorkPermitMember.id == member_id,
        WorkPermitMember.work_permit_id == work_permit_id,
        WorkPermitMember.tenant_id == tenant_id,
    )
    member = (await session.execute(stmt)).scalar_one_or_none()
    if member is None:
        return False
    await session.delete(member)
    await session.flush()
    return True


async def list_members(
    session: AsyncSession, *, tenant_id: str, work_permit_id: str,
) -> list[WorkPermitMember]:
    stmt = select(WorkPermitMember).where(
        WorkPermitMember.tenant_id == tenant_id,
        WorkPermitMember.work_permit_id == work_permit_id,
    ).order_by(WorkPermitMember.created_at.asc())
    return list((await session.execute(stmt)).scalars().all())


async def list_events(
    session: AsyncSession, *, tenant_id: str, work_permit_id: str,
) -> list[WorkPermitEvent]:
    stmt = select(WorkPermitEvent).where(
        WorkPermitEvent.tenant_id == tenant_id,
        WorkPermitEvent.work_permit_id == work_permit_id,
    ).order_by(WorkPermitEvent.at.asc(), WorkPermitEvent.created_at.asc())
    return list((await session.execute(stmt)).scalars().all())


async def _transition(
    session: AsyncSession, *, tenant_id: str, work_permit_id: str, target: str,
    event_type: str, actor_user_id: str | None, photo_file_id: str | None = None,
    note: str | None = None,
) -> WorkPermit | None:
    wp = await _get(session, tenant_id, work_permit_id)
    if wp is None:
        return None
    lc.validate_transition(str(wp.status), target)
    wp.status = target
    if target == lc.STATUS_ISSUED and wp.opened_at is None:
        wp.opened_at = _now()
    if target == lc.STATUS_SUSPENDED:
        wp.suspended_at = _now()
    if target == lc.STATUS_CLOSED:
        wp.closed_at = _now()
    await _log(
        session, tenant_id=tenant_id, work_permit_id=work_permit_id,
        event_type=event_type, actor_user_id=actor_user_id,
        photo_file_id=photo_file_id, note=note,
    )
    await session.flush()
    await session.refresh(wp)
    return wp


async def issue(session, *, tenant_id, work_permit_id, actor_user_id, photo_file_id=None, note=None):
    from app.services.work_permit_admission import enforce_brigade_readiness

    if await _get(session, tenant_id, work_permit_id) is None:
        return None
    await enforce_brigade_readiness(session, tenant_id=tenant_id, work_permit_id=work_permit_id)
    return await _transition(
        session, tenant_id=tenant_id, work_permit_id=work_permit_id, target=lc.STATUS_ISSUED,
        event_type="issued", actor_user_id=actor_user_id, photo_file_id=photo_file_id, note=note,
    )


async def suspend(session, *, tenant_id, work_permit_id, actor_user_id, note=None):
    return await _transition(
        session, tenant_id=tenant_id, work_permit_id=work_permit_id, target=lc.STATUS_SUSPENDED,
        event_type="suspended", actor_user_id=actor_user_id, note=note,
    )


async def resume(session, *, tenant_id, work_permit_id, actor_user_id, note=None):
    return await _transition(
        session, tenant_id=tenant_id, work_permit_id=work_permit_id, target=lc.STATUS_ISSUED,
        event_type="resumed", actor_user_id=actor_user_id, note=note,
    )


async def close(session, *, tenant_id, work_permit_id, actor_user_id, photo_file_id=None, note=None):
    return await _transition(
        session, tenant_id=tenant_id, work_permit_id=work_permit_id, target=lc.STATUS_CLOSED,
        event_type="closed", actor_user_id=actor_user_id, photo_file_id=photo_file_id, note=note,
    )


async def cancel(session, *, tenant_id, work_permit_id, actor_user_id, note=None):
    return await _transition(
        session, tenant_id=tenant_id, work_permit_id=work_permit_id, target=lc.STATUS_CANCELLED,
        event_type="cancelled", actor_user_id=actor_user_id, note=note,
    )


async def extend(session, *, tenant_id, work_permit_id, planned_end, actor_user_id, note=None):
    wp = await _get(session, tenant_id, work_permit_id)
    if wp is None:
        return None
    if wp.status not in (lc.STATUS_ISSUED, lc.STATUS_SUSPENDED):
        raise lc.WorkPermitTransitionError(str(wp.status), "extend")
    wp.planned_end = planned_end
    await _log(
        session, tenant_id=tenant_id, work_permit_id=work_permit_id,
        event_type="extended", actor_user_id=actor_user_id, note=note,
    )
    await session.flush()
    await session.refresh(wp)
    return wp


# --- целевой инструктаж (Ф2) ------------------------------------------------

async def create_briefing(
    session: AsyncSession, *, tenant_id: str, work_permit_id: str,
    conducted_by_person_id: str | None = None, conducted_at: datetime | None = None,
    topics_text: str | None = None,
) -> WorkPermitBriefing | None:
    wp = await _get(session, tenant_id, work_permit_id)
    if wp is None:
        return None
    br = WorkPermitBriefing(
        tenant_id=tenant_id, work_permit_id=work_permit_id,
        conducted_by_person_id=conducted_by_person_id, conducted_at=conducted_at,
        topics_text=topics_text,
    )
    session.add(br)
    await session.flush()
    await session.refresh(br)
    return br


async def list_briefings(
    session: AsyncSession, *, tenant_id: str, work_permit_id: str,
) -> list[WorkPermitBriefing]:
    stmt = select(WorkPermitBriefing).where(
        WorkPermitBriefing.tenant_id == tenant_id,
        WorkPermitBriefing.work_permit_id == work_permit_id,
    ).order_by(WorkPermitBriefing.created_at.asc())
    return list((await session.execute(stmt)).scalars().all())


async def get_briefing(
    session: AsyncSession, *, tenant_id: str, briefing_id: str,
) -> WorkPermitBriefing | None:
    stmt = select(WorkPermitBriefing).where(
        WorkPermitBriefing.id == briefing_id, WorkPermitBriefing.tenant_id == tenant_id,
    )
    return (await session.execute(stmt)).scalar_one_or_none()


_BRIEFING_EDITABLE = ("conducted_by_person_id", "conducted_at", "topics_text")


async def update_briefing(
    session: AsyncSession, *, tenant_id: str, briefing_id: str, **fields,
) -> WorkPermitBriefing | None:
    br = await get_briefing(session, tenant_id=tenant_id, briefing_id=briefing_id)
    if br is None:
        return None
    for key, value in fields.items():
        if key in _BRIEFING_EDITABLE:
            setattr(br, key, value)
    await session.flush()
    await session.refresh(br)
    return br
