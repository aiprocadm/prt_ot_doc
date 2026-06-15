from datetime import date, timedelta

import pytest

from app.domains.permits import lifecycle as lc
from app.domains.permits import service as svc


@pytest.mark.asyncio
async def test_expire_due_idempotent(sessionmaker, data_factory):
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

        first = await svc.expire_due(session, tenant_id=person.tenant_id)
        second = await svc.expire_due(session, tenant_id=person.tenant_id)
        assert first == 1
        assert second == 0  # already expired — idempotent
