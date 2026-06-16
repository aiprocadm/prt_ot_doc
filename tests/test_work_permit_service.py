from datetime import date, datetime, timedelta, timezone

import pytest

from app.domains.permits import service as permit_svc
from app.domains.work_permits import lifecycle as lc
from app.domains.work_permits import service as svc


def _now():
    return datetime(2026, 6, 16, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_create_add_member_issue_suspend_resume_close(sessionmaker, data_factory):
    person = await data_factory.create_person()
    async with sessionmaker() as session:
        wp = await svc.create_work_permit(
            session, tenant_id=person.tenant_id, work_type="hot_work",
            zone_text="Цех 1", number="НД-1",
        )
        assert wp.status == lc.STATUS_DRAFT

        member = await svc.add_member(
            session, tenant_id=person.tenant_id, work_permit_id=wp.id,
            person_id=person.id, role="foreman",
        )
        assert member.role == "foreman"

        # brigade-readiness gate: member needs an active personal permit to issue
        await permit_svc.create_permit(
            session, tenant_id=person.tenant_id, person_id=person.id,
            permit_type="hot_work", issued_at=date.today(),
            valid_until=date.today() + timedelta(days=30),
        )

        issued = await svc.issue(session, tenant_id=person.tenant_id, work_permit_id=wp.id, actor_user_id="u1")
        assert issued.status == lc.STATUS_ISSUED
        assert issued.opened_at is not None

        sus = await svc.suspend(session, tenant_id=person.tenant_id, work_permit_id=wp.id, actor_user_id="u1")
        assert sus.status == lc.STATUS_SUSPENDED
        res = await svc.resume(session, tenant_id=person.tenant_id, work_permit_id=wp.id, actor_user_id="u1")
        assert res.status == lc.STATUS_ISSUED
        closed = await svc.close(session, tenant_id=person.tenant_id, work_permit_id=wp.id, actor_user_id="u1")
        assert closed.status == lc.STATUS_CLOSED

        events = await svc.list_events(session, tenant_id=person.tenant_id, work_permit_id=wp.id)
        assert [e.event_type for e in events] == ["issued", "suspended", "resumed", "closed"]


@pytest.mark.asyncio
async def test_update_only_in_draft(sessionmaker, data_factory):
    person = await data_factory.create_person()
    async with sessionmaker() as session:
        wp = await svc.create_work_permit(
            session, tenant_id=person.tenant_id, work_type="height", zone_text="Кровля",
        )
        await svc.issue(session, tenant_id=person.tenant_id, work_permit_id=wp.id, actor_user_id="u1")
        with pytest.raises(lc.WorkPermitTransitionError):
            await svc.update_work_permit(
                session, tenant_id=person.tenant_id, work_permit_id=wp.id, zone_text="x",
            )


@pytest.mark.asyncio
async def test_cancel_and_extend(sessionmaker, data_factory):
    person = await data_factory.create_person()
    async with sessionmaker() as session:
        wp = await svc.create_work_permit(
            session, tenant_id=person.tenant_id, work_type="electrical", zone_text="ТП-3",
        )
        await svc.issue(session, tenant_id=person.tenant_id, work_permit_id=wp.id, actor_user_id="u1")
        extended = await svc.extend(
            session, tenant_id=person.tenant_id, work_permit_id=wp.id,
            planned_end=_now(), actor_user_id="u1",
        )
        # SQLite stores DateTime(timezone=True) as naive — compare tz-stripped (repo convention)
        assert extended.planned_end == _now().replace(tzinfo=None)
        cancelled = await svc.cancel(session, tenant_id=person.tenant_id, work_permit_id=wp.id, actor_user_id="u1")
        assert cancelled.status == lc.STATUS_CANCELLED
