from datetime import date, timedelta

import pytest

from app.domains.permits import service as permit_svc
from app.domains.work_permits import lifecycle as lc
from app.domains.work_permits import service as svc
from app.services import work_permit_admission as gate


@pytest.mark.asyncio
async def test_expired_personal_permit_blocks_issue(sessionmaker, data_factory):
    person = await data_factory.create_person()
    async with sessionmaker() as session:
        # personal permit that is already expired
        await permit_svc.create_permit(
            session, tenant_id=person.tenant_id, person_id=person.id,
            permit_type="height", issued_at=date.today() - timedelta(days=10),
            valid_until=date.today() - timedelta(days=1),
        )
        wp = await svc.create_work_permit(
            session, tenant_id=person.tenant_id, work_type="height", zone_text="Кровля",
        )
        await svc.add_member(
            session, tenant_id=person.tenant_id, work_permit_id=wp.id,
            person_id=person.id, role="foreman",
        )
        report = await gate.check_brigade_readiness(
            session, tenant_id=person.tenant_id, work_permit_id=wp.id,
        )
        assert report.ok is False
        assert any(v.code == "permit_expired" and v.severity == "block" for v in report.violations)

        with pytest.raises(gate.WorkPermitBlocked):
            await svc.issue(session, tenant_id=person.tenant_id, work_permit_id=wp.id, actor_user_id="u1")


@pytest.mark.asyncio
async def test_active_personal_permit_allows_issue(sessionmaker, data_factory):
    person = await data_factory.create_person()
    async with sessionmaker() as session:
        await permit_svc.create_permit(
            session, tenant_id=person.tenant_id, person_id=person.id,
            permit_type="height", issued_at=date.today(),
            valid_until=date.today() + timedelta(days=30),
        )
        wp = await svc.create_work_permit(
            session, tenant_id=person.tenant_id, work_type="height", zone_text="Кровля",
        )
        await svc.add_member(
            session, tenant_id=person.tenant_id, work_permit_id=wp.id,
            person_id=person.id, role="foreman",
        )
        issued = await svc.issue(session, tenant_id=person.tenant_id, work_permit_id=wp.id, actor_user_id="u1")
        assert issued.status == lc.STATUS_ISSUED
        # medical/training absent → warnings, not blocks
        report = await gate.check_brigade_readiness(
            session, tenant_id=person.tenant_id, work_permit_id=wp.id,
        )
        assert all(v.severity == "warn" for v in report.violations)
