"""Ф3b домен: PEP_PURPOSES + детерминированный снимок closing + closing_readiness."""
from __future__ import annotations

import pytest

from app.domains.signing.pep import PEP_PURPOSES


def test_pep_purposes_has_closing():
    assert "work_permit_closing" in PEP_PURPOSES


@pytest.mark.asyncio
async def test_closing_snapshot_is_deterministic(sessionmaker, data_factory):
    from app.services.pep_signing import PepSigningService
    from app.domains.work_permits import service as svc

    async with sessionmaker() as session:
        person = await data_factory.create_person(session)
        wp = await svc.create_work_permit(
            session, tenant_id=person.tenant_id, work_type="height", zone_text="z",
            number="НД-1",
        )
        await svc.record_completion(
            session, tenant_id=person.tenant_id, work_permit_id=wp.id,
            completion_text="работы окончены, место сдано", actor_user_id="u1",
        )
        ps = PepSigningService(session, person.tenant_id)
        a = await ps._build_content("work_permit_closing", wp.id)
        b = await ps._build_content("work_permit_closing", wp.id)
        assert a == b
        assert a["work_permit_id"] == wp.id
        assert a["completion_text"] == "работы окончены, место сдано"
