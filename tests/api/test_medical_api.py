from __future__ import annotations

from datetime import date

import pytest
from fastapi import status

from app.models.models import RoleEnum


async def _seed_person(sessionmaker, data_factory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        person = await data_factory.create_person(tenant=tenant, company=company, session=session)
        await session.commit()
        return person.id


@pytest.mark.asyncio
async def test_record_exam_unfit_blocks_then_fit_clears(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    person_id = await _seed_person(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)

    r = await async_client.post("/api/v1/medical/exams", headers=headers, json={
        "person_id": person_id, "exam_kind": "periodic",
        "exam_date": date(2026, 1, 1).isoformat(), "fitness": "unfit",
        "contraindications": ["asthma"]})
    assert r.status_code == status.HTTP_201_CREATED, r.text
    assert r.json()["fitness"] == "unfit"

    s = await async_client.get("/api/v1/medical/suspensions", headers=headers,
                               params={"person_id": person_id})
    assert s.status_code == status.HTTP_200_OK
    assert s.json()["total"] == 1

    r2 = await async_client.post("/api/v1/medical/exams", headers=headers, json={
        "person_id": person_id, "exam_kind": "periodic",
        "exam_date": date(2026, 2, 1).isoformat(), "fitness": "fit"})
    assert r2.status_code == status.HTTP_201_CREATED
    s2 = await async_client.get("/api/v1/medical/suspensions", headers=headers,
                                params={"person_id": person_id, "status": "active"})
    assert s2.json()["total"] == 0
