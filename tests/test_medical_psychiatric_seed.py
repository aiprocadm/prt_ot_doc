"""seed_default_activity_types is idempotent and loads the standard 695 set."""

import pytest

from app.domains.medical.psychiatric_defaults import PSYCHIATRIC_ACTIVITY_DEFAULTS
from app.domains.medical.service import seed_default_activity_types
from app.models.models import PsychiatricActivityType
from sqlalchemy import func, select


@pytest.mark.asyncio
async def test_seed_defaults_idempotent(sessionmaker, data_factory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        n1 = await seed_default_activity_types(session, tenant_id=str(tenant.id))
        await session.commit()
        n2 = await seed_default_activity_types(session, tenant_id=str(tenant.id))
        await session.commit()
        total = await session.scalar(
            select(func.count()).select_from(PsychiatricActivityType).where(
                PsychiatricActivityType.tenant_id == tenant.id
            )
        )
    assert n1 == len(PSYCHIATRIC_ACTIVITY_DEFAULTS)
    assert n2 == 0  # second run inserts nothing
    assert int(total) == len(PSYCHIATRIC_ACTIVITY_DEFAULTS)
