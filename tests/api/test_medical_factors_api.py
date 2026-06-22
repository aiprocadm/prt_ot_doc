from __future__ import annotations

import pytest
from fastapi import status

from app.models.models import RoleEnum


@pytest.mark.asyncio
async def test_factor_crud_and_duplicate_code(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    body = {
        "code": "4.4",
        "name": "Шум",
        "category": "factor",
        "exam_kinds": ["periodic"],
        "periodicity_months": 12,
    }
    r = await async_client.post("/api/v1/medical/factors", headers=headers, json=body)
    assert r.status_code == status.HTTP_201_CREATED, r.text
    fid = r.json()["id"]

    r2 = await async_client.post("/api/v1/medical/factors", headers=headers, json=body)
    assert r2.status_code == status.HTTP_409_CONFLICT

    r3 = await async_client.get("/api/v1/medical/factors", headers=headers)
    assert r3.status_code == status.HTTP_200_OK
    assert any(f["code"] == "4.4" for f in r3.json()["items"])

    r4 = await async_client.patch(
        f"/api/v1/medical/factors/{fid}", headers=headers, json={"periodicity_months": 24}
    )
    assert r4.status_code == status.HTTP_200_OK and r4.json()["periodicity_months"] == 24

    r5 = await async_client.delete(f"/api/v1/medical/factors/{fid}", headers=headers)
    assert r5.status_code == status.HTTP_204_NO_CONTENT


@pytest.mark.asyncio
async def test_factors_require_write_role(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.LINE_MANAGER)
    r = await async_client.post(
        "/api/v1/medical/factors",
        headers=headers,
        json={"code": "x", "name": "y", "exam_kinds": ["periodic"]},
    )
    assert r.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)
