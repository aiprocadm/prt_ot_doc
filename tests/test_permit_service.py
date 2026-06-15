"""TDD tests for backend/app/domains/permits/service.py — Task 3 (TZ-3.4)."""
from datetime import date, timedelta

import pytest

from app.domains.permits import lifecycle as lc
from app.domains.permits import service as svc


@pytest.mark.asyncio
async def test_create_then_revoke(sessionmaker, data_factory):
    person = await data_factory.create_person()
    async with sessionmaker() as session:
        permit = await svc.create_permit(
            session, tenant_id=person.tenant_id, person_id=person.id,
            permit_type="Работа на высоте", issued_at=date.today(),
            valid_until=date.today() + timedelta(days=30), position_id=None,
        )
        assert permit.status == lc.PERMIT_STATUS_ACTIVE

        revoked = await svc.revoke_permit(session, tenant_id=person.tenant_id, permit_id=permit.id)
        assert revoked.status == lc.PERMIT_STATUS_REVOKED

        with pytest.raises(lc.PermitTransitionError):  # revoked is terminal
            await svc.revoke_permit(session, tenant_id=person.tenant_id, permit_id=permit.id)


@pytest.mark.asyncio
async def test_create_already_expired_is_expired(sessionmaker, data_factory):
    person = await data_factory.create_person()
    async with sessionmaker() as session:
        permit = await svc.create_permit(
            session, tenant_id=person.tenant_id, person_id=person.id,
            permit_type="Огневые работы", issued_at=date.today() - timedelta(days=10),
            valid_until=date.today() - timedelta(days=1), position_id=None,
        )
        assert permit.status == lc.PERMIT_STATUS_EXPIRED


@pytest.mark.asyncio
async def test_extend_revalidates_expired(sessionmaker, data_factory):
    person = await data_factory.create_person()
    async with sessionmaker() as session:
        permit = await svc.create_permit(
            session, tenant_id=person.tenant_id, person_id=person.id,
            permit_type="Газоопасные работы", issued_at=date.today() - timedelta(days=10),
            valid_until=date.today() - timedelta(days=1), position_id=None,
        )
        assert permit.status == lc.PERMIT_STATUS_EXPIRED
        extended = await svc.extend_permit(
            session, tenant_id=person.tenant_id, permit_id=permit.id,
            valid_until=date.today() + timedelta(days=60),
        )
        assert extended.status == lc.PERMIT_STATUS_ACTIVE


@pytest.mark.asyncio
async def test_extend_revoked_is_rejected(sessionmaker, data_factory):
    person = await data_factory.create_person()
    async with sessionmaker() as session:
        permit = await svc.create_permit(
            session, tenant_id=person.tenant_id, person_id=person.id,
            permit_type="x", issued_at=date.today(), valid_until=None, position_id=None,
        )
        await svc.revoke_permit(session, tenant_id=person.tenant_id, permit_id=permit.id)
        with pytest.raises(lc.PermitTransitionError):
            await svc.extend_permit(
                session, tenant_id=person.tenant_id, permit_id=permit.id,
                valid_until=date.today() + timedelta(days=30),
            )


@pytest.mark.asyncio
async def test_update_non_active_conflicts(sessionmaker, data_factory):
    person = await data_factory.create_person()
    async with sessionmaker() as session:
        permit = await svc.create_permit(
            session, tenant_id=person.tenant_id, person_id=person.id,
            permit_type="x", issued_at=date.today(), valid_until=None, position_id=None,
        )
        await svc.revoke_permit(session, tenant_id=person.tenant_id, permit_id=permit.id)
        with pytest.raises(lc.PermitTransitionError):
            await svc.update_permit(
                session, tenant_id=person.tenant_id, permit_id=permit.id, permit_type="y",
            )


@pytest.mark.asyncio
async def test_expire_due_flips_overdue_active(sessionmaker, data_factory):
    person = await data_factory.create_person()
    async with sessionmaker() as session:
        permit = await svc.create_permit(
            session, tenant_id=person.tenant_id, person_id=person.id,
            permit_type="a", issued_at=date.today() - timedelta(days=5),
            valid_until=date.today() + timedelta(days=5), position_id=None,
        )
        permit.valid_until = date.today() - timedelta(days=1)
        permit.status = lc.PERMIT_STATUS_ACTIVE
        await session.flush()

        count = await svc.expire_due(session, tenant_id=person.tenant_id)
        assert count == 1
        await session.refresh(permit)
        assert permit.status == lc.PERMIT_STATUS_EXPIRED
