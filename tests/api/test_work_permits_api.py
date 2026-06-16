from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi import status

from app.models.models import RoleEnum

BASE = "/api/v1/work-permits"


@pytest.mark.asyncio
async def test_work_permit_crud_and_members(async_client, make_auth_headers, data_factory, sessionmaker):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    person = await data_factory.create_person()

    r = await async_client.post(BASE, headers=headers, json={
        "work_type": "hot_work", "zone_text": "Цех 1", "number": "НД-100",
    })
    assert r.status_code == status.HTTP_201_CREATED, r.text
    wp_id = r.json()["id"]
    assert r.json()["status"] == "draft"

    r = await async_client.get(BASE, headers=headers, params={"status": "draft"})
    assert r.status_code == status.HTTP_200_OK
    assert r.json()["total"] >= 1

    r = await async_client.patch(f"{BASE}/{wp_id}", headers=headers, json={"zone_text": "Цех 2"})
    assert r.status_code == status.HTTP_200_OK
    assert r.json()["zone_text"] == "Цех 2"

    r = await async_client.post(f"{BASE}/{wp_id}/members", headers=headers, json={
        "person_id": str(person.id), "role": "foreman",
    })
    assert r.status_code == status.HTTP_201_CREATED, r.text
    member_id = r.json()["id"]

    r = await async_client.get(f"{BASE}/{wp_id}", headers=headers)
    assert any(m["id"] == member_id for m in r.json()["members"])

    r = await async_client.delete(f"{BASE}/{wp_id}/members/{member_id}", headers=headers)
    assert r.status_code == status.HTTP_204_NO_CONTENT


@pytest.mark.asyncio
async def test_create_member_unknown_person_404(async_client, make_auth_headers, data_factory):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    r = await async_client.post(BASE, headers=headers, json={"work_type": "height", "zone_text": "z"})
    wp_id = r.json()["id"]
    r = await async_client.post(f"{BASE}/{wp_id}/members", headers=headers, json={
        "person_id": "missing", "role": "member",
    })
    assert r.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_invalid_work_type_422(async_client, make_auth_headers, data_factory):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    r = await async_client.post(BASE, headers=headers, json={"work_type": "nope", "zone_text": "z"})
    assert r.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@pytest.mark.asyncio
async def test_work_permits_tenant_isolated(async_client, make_auth_headers, data_factory, sessionmaker):
    headers = await make_auth_headers(RoleEnum.ADMIN)  # tenant "test"
    from app.models.work_permit import WorkPermit
    async with sessionmaker() as session:
        other = await data_factory.ensure_tenant(slug="other", session=session)
        wp = WorkPermit(tenant_id=other.id, work_type="height", zone_text="чужая", status="draft")
        session.add(wp)
        await session.commit()
        foreign_id = str(wp.id)
    assert (await async_client.get(f"{BASE}/{foreign_id}", headers=headers)).status_code == status.HTTP_404_NOT_FOUND
    listed = await async_client.get(BASE, headers=headers)
    assert all(item["id"] != foreign_id for item in listed.json()["items"])
