from datetime import date, datetime, timedelta, timezone

import pytest

from app.domains.permits import service as permit_svc
from app.domains.work_permits import lifecycle as lc
from app.domains.work_permits import service as svc


def _now():
    return datetime(2026, 6, 16, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_create_add_member_issue_suspend_resume_close(sessionmaker, data_factory):
    # Создаём тенант+компанию один раз; обе персоны используют ту же компанию,
    # чтобы не нарушить UNIQUE (tenant_id, name) на таблице company.
    tenant = await data_factory.ensure_tenant()
    company = await data_factory.create_company(tenant=tenant)
    person = await data_factory.create_person(
        tenant=tenant, company=company, first_name="Fore", last_name="Man"
    )
    supervisor = await data_factory.create_person(
        tenant=tenant, company=company, first_name="Super", last_name="Visor"
    )
    async with sessionmaker() as session:
        wp = await svc.create_work_permit(
            session,
            tenant_id=person.tenant_id,
            work_type="hot_work",
            zone_text="Цех 1",
            number="НД-1",
        )
        assert wp.status == lc.STATUS_DRAFT

        member = await svc.add_member(
            session,
            tenant_id=person.tenant_id,
            work_permit_id=wp.id,
            person_id=person.id,
            role="foreman",
        )
        assert member.role == "foreman"

        # brigade-readiness gate: member needs an active personal permit to issue
        await permit_svc.create_permit(
            session,
            tenant_id=person.tenant_id,
            person_id=person.id,
            permit_type="hot_work",
            issued_at=date.today(),
            valid_until=date.today() + timedelta(days=30),
        )

        issued = await svc.issue(
            session, tenant_id=person.tenant_id, work_permit_id=wp.id, actor_user_id="u1"
        )
        assert issued.status == lc.STATUS_ISSUED
        assert issued.opened_at is not None

        sus = await svc.suspend(
            session, tenant_id=person.tenant_id, work_permit_id=wp.id, actor_user_id="u1"
        )
        assert sus.status == lc.STATUS_SUSPENDED
        res = await svc.resume(
            session, tenant_id=person.tenant_id, work_permit_id=wp.id, actor_user_id="u1"
        )
        assert res.status == lc.STATUS_ISSUED

        # Ф3b: закрытие гейтится актом + подписями «сдал» (foreman) + «принял» (supervisor)
        from app.domains.work_permits.signing import sign_closing

        await svc.add_member(
            session,
            tenant_id=person.tenant_id,
            work_permit_id=wp.id,
            person_id=supervisor.id,
            role="supervisor",
        )
        await svc.record_completion(
            session,
            tenant_id=person.tenant_id,
            work_permit_id=wp.id,
            completion_text="готово",
            actor_user_id="u1",
        )
        await sign_closing(
            session,
            tenant_id=str(person.tenant_id),
            work_permit_id=wp.id,
            person_id=person.id,
            mode="attested",
            requested_by="u1",
        )
        await sign_closing(
            session,
            tenant_id=str(person.tenant_id),
            work_permit_id=wp.id,
            person_id=supervisor.id,
            mode="attested",
            requested_by="u1",
        )

        closed = await svc.close(
            session, tenant_id=person.tenant_id, work_permit_id=wp.id, actor_user_id="u1"
        )
        assert closed.status == lc.STATUS_CLOSED

        events = await svc.list_events(session, tenant_id=person.tenant_id, work_permit_id=wp.id)
        # Последовательность: member_added(foreman) + issued + suspended + resumed +
        # member_added(supervisor) + closed — проверяем только что closed последний
        assert events[-1].event_type == "closed"
        fsm_events = [
            e.event_type
            for e in events
            if e.event_type in {"issued", "suspended", "resumed", "closed"}
        ]
        assert fsm_events == ["issued", "suspended", "resumed", "closed"]


@pytest.mark.asyncio
async def test_update_only_in_draft(sessionmaker, data_factory):
    person = await data_factory.create_person()
    async with sessionmaker() as session:
        wp = await svc.create_work_permit(
            session,
            tenant_id=person.tenant_id,
            work_type="height",
            zone_text="Кровля",
        )
        await svc.issue(
            session, tenant_id=person.tenant_id, work_permit_id=wp.id, actor_user_id="u1"
        )
        with pytest.raises(lc.WorkPermitTransitionError):
            await svc.update_work_permit(
                session,
                tenant_id=person.tenant_id,
                work_permit_id=wp.id,
                zone_text="x",
            )


@pytest.mark.asyncio
async def test_cancel_and_extend(sessionmaker, data_factory):
    person = await data_factory.create_person()
    async with sessionmaker() as session:
        wp = await svc.create_work_permit(
            session,
            tenant_id=person.tenant_id,
            work_type="electrical",
            zone_text="ТП-3",
        )
        await svc.issue(
            session, tenant_id=person.tenant_id, work_permit_id=wp.id, actor_user_id="u1"
        )
        extended = await svc.extend(
            session,
            tenant_id=person.tenant_id,
            work_permit_id=wp.id,
            planned_end=_now(),
            actor_user_id="u1",
        )
        # SQLite stores DateTime(timezone=True) as naive — compare tz-stripped (repo convention)
        assert extended.planned_end == _now().replace(tzinfo=None)
        cancelled = await svc.cancel(
            session, tenant_id=person.tenant_id, work_permit_id=wp.id, actor_user_id="u1"
        )
        assert cancelled.status == lc.STATUS_CANCELLED


@pytest.mark.asyncio
async def test_create_persists_782n_fields(sessionmaker, data_factory):
    person = await data_factory.create_person()
    async with sessionmaker() as session:
        wp = await svc.create_work_permit(
            session,
            tenant_id=person.tenant_id,
            work_type="height",
            zone_text="z",
            content_text="монтаж",
            safety_systems=["fall_arrest"],
            ppe_text="каска",
        )
        assert wp.content_text == "монтаж"
        assert wp.safety_systems == ["fall_arrest"]

        updated = await svc.update_work_permit(
            session,
            tenant_id=person.tenant_id,
            work_permit_id=wp.id,
            conditions_text="высота 8м",
            safety_systems=["restraint", "access"],
        )
        assert updated.conditions_text == "высота 8м"
        assert updated.safety_systems == ["restraint", "access"]


@pytest.mark.asyncio
async def test_briefing_crud(sessionmaker, data_factory):
    from app.domains.work_permits import (
        create_briefing,
        create_work_permit,
        get_briefing,
        list_briefings,
        update_briefing,
    )

    person = await data_factory.create_person()
    async with sessionmaker() as session:
        wp = await create_work_permit(
            session,
            tenant_id=person.tenant_id,
            work_type="height",
            zone_text="z",
        )
        br = await create_briefing(
            session,
            tenant_id=person.tenant_id,
            work_permit_id=wp.id,
            topics_text="страховка",
        )
        assert br.work_permit_id == wp.id
        assert br.topics_text == "страховка"

        rows = await list_briefings(session, tenant_id=person.tenant_id, work_permit_id=wp.id)
        assert [b.id for b in rows] == [br.id]

        updated = await update_briefing(
            session,
            tenant_id=person.tenant_id,
            briefing_id=br.id,
            topics_text="страховка + СИЗ",
        )
        assert updated.topics_text == "страховка + СИЗ"

        again = await get_briefing(session, tenant_id=person.tenant_id, briefing_id=br.id)
        assert again.topics_text == "страховка + СИЗ"


@pytest.mark.asyncio
async def test_create_briefing_unknown_permit_returns_none(sessionmaker, data_factory):
    from app.domains.work_permits import create_briefing

    person = await data_factory.create_person()
    async with sessionmaker() as session:
        assert (
            await create_briefing(
                session,
                tenant_id=person.tenant_id,
                work_permit_id="missing",
            )
            is None
        )


@pytest.mark.asyncio
async def test_extend_logs_old_and_new_end(sessionmaker, data_factory):
    from datetime import datetime, timezone

    from app.domains.work_permits import create_work_permit, extend, issue, list_events

    person = await data_factory.create_person()
    async with sessionmaker() as session:
        wp = await create_work_permit(
            session,
            tenant_id=person.tenant_id,
            work_type="height",
            zone_text="z",
            planned_end=datetime(2026, 6, 18, tzinfo=timezone.utc),
        )
        await issue(session, tenant_id=person.tenant_id, work_permit_id=wp.id, actor_user_id="u1")
        new_end = datetime(2026, 6, 20, tzinfo=timezone.utc)
        await extend(
            session,
            tenant_id=person.tenant_id,
            work_permit_id=wp.id,
            planned_end=new_end,
            actor_user_id="u1",
        )
        events = await list_events(session, tenant_id=person.tenant_id, work_permit_id=wp.id)
        ext = [e for e in events if e.event_type == "extended"][-1]
        assert ext.meta["new_end"].startswith("2026-06-20")
        assert ext.meta["old_end"].startswith("2026-06-18")


@pytest.mark.asyncio
async def test_member_changes_are_logged(sessionmaker, data_factory):
    from app.domains.work_permits import add_member, create_work_permit, list_events, remove_member

    # Reuse person as the brigade member (same tenant, avoids second company creation)
    person = await data_factory.create_person()
    async with sessionmaker() as session:
        wp = await create_work_permit(
            session,
            tenant_id=person.tenant_id,
            work_type="height",
            zone_text="z",
        )
        m = await add_member(
            session,
            tenant_id=person.tenant_id,
            work_permit_id=wp.id,
            person_id=person.id,
            role="member",
            actor_user_id="u1",
        )
        await remove_member(
            session,
            tenant_id=person.tenant_id,
            work_permit_id=wp.id,
            member_id=m.id,
            actor_user_id="u1",
        )
        events = await list_events(session, tenant_id=person.tenant_id, work_permit_id=wp.id)
        types = [e.event_type for e in events]
        assert "member_added" in types and "member_removed" in types
        added = [e for e in events if e.event_type == "member_added"][0]
        assert added.meta == {"person_id": person.id, "role": "member"}


@pytest.mark.asyncio
async def test_daily_admission_requires_issued(sessionmaker, data_factory):
    from datetime import date

    from app.domains.work_permits import create_admission, create_work_permit, issue
    from app.domains.work_permits.lifecycle import WorkPermitTransitionError

    person = await data_factory.create_person()
    async with sessionmaker() as session:
        wp = await create_work_permit(
            session,
            tenant_id=person.tenant_id,
            work_type="height",
            zone_text="z",
        )
        # draft → нельзя
        with pytest.raises(WorkPermitTransitionError):
            await create_admission(
                session,
                tenant_id=person.tenant_id,
                work_permit_id=wp.id,
                admission_date=date(2026, 6, 18),
            )
        await issue(session, tenant_id=person.tenant_id, work_permit_id=wp.id, actor_user_id="u1")
        adm = await create_admission(
            session,
            tenant_id=person.tenant_id,
            work_permit_id=wp.id,
            admission_date=date(2026, 6, 18),
            note="смена 1",
        )
        assert adm.admission_date == date(2026, 6, 18)
        assert adm.note == "смена 1"


@pytest.mark.asyncio
async def test_daily_admission_list_and_update(sessionmaker, data_factory):
    from datetime import date, datetime, timezone

    from app.domains.work_permits import (
        create_admission,
        create_work_permit,
        issue,
        list_admissions,
        update_admission,
    )

    person = await data_factory.create_person()
    async with sessionmaker() as session:
        wp = await create_work_permit(
            session,
            tenant_id=person.tenant_id,
            work_type="height",
            zone_text="z",
        )
        await issue(session, tenant_id=person.tenant_id, work_permit_id=wp.id, actor_user_id="u1")
        adm = await create_admission(
            session,
            tenant_id=person.tenant_id,
            work_permit_id=wp.id,
            admission_date=date(2026, 6, 18),
        )
        rows = await list_admissions(session, tenant_id=person.tenant_id, work_permit_id=wp.id)
        assert [a.id for a in rows] == [adm.id]
        end = datetime(2026, 6, 18, 17, tzinfo=timezone.utc)
        upd = await update_admission(
            session,
            tenant_id=person.tenant_id,
            admission_id=adm.id,
            end_at=end,
        )
        # SQLite stores DateTime(timezone=True) as naive — compare tz-stripped (repo convention)
        assert upd.end_at == end.replace(tzinfo=None)


@pytest.mark.asyncio
async def test_create_and_edit_persists_type_specific(sessionmaker, data_factory):
    tenant = await data_factory.ensure_tenant()
    tid = str(tenant.id)
    async with sessionmaker() as session:
        wp = await svc.create_work_permit(
            session,
            tenant_id=tid,
            work_type="confined_space",
            zone_text="колодец",
            type_specific={"ventilation": "forced"},
        )
        assert wp.type_specific == {"ventilation": "forced"}
        edited = await svc.update_work_permit(
            session, tenant_id=tid, work_permit_id=wp.id, type_specific={"ventilation": "natural"}
        )
        assert edited.type_specific == {"ventilation": "natural"}
