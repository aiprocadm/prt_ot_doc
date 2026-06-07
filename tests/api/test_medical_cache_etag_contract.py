from __future__ import annotations

import pytest
from fastapi import status
from app.models.models import Position, RoleEnum


async def _seed_pos(sessionmaker, data_factory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        pos = Position(tenant_id=tenant.id, company_id=company.id, name="ETagPos")
        session.add(pos); await session.commit(); return pos.id


@pytest.mark.asyncio
async def test_norms_etag_hit_miss_invalidation(async_client, sessionmaker, data_factory, make_auth_headers):
    pos_id = await _seed_pos(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)
    first = await async_client.get("/api/v1/medical/norms", headers=headers)
    assert first.status_code == status.HTTP_200_OK
    etag = first.headers["ETag"]
    hit = await async_client.get("/api/v1/medical/norms", headers={**headers, "If-None-Match": etag})
    assert hit.status_code == status.HTTP_304_NOT_MODIFIED
    miss = await async_client.get("/api/v1/medical/norms", headers={**headers, "If-None-Match": '"bogus"'})
    assert miss.status_code == status.HTTP_200_OK
    await async_client.post("/api/v1/medical/norms", headers=headers,
                            json={"position_id": pos_id, "exam_kind": "periodic", "interval_days": 365})
    after = await async_client.get("/api/v1/medical/norms", headers={**headers, "If-None-Match": etag})
    assert after.status_code == status.HTTP_200_OK  # ETag changed after create
    assert after.headers["ETag"] != etag
