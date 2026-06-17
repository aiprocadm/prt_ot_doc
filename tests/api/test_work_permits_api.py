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


@pytest.mark.asyncio
async def test_issue_blocked_then_allowed_with_permit(async_client, make_auth_headers, data_factory, sessionmaker):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    person = await data_factory.create_person()
    r = await async_client.post(BASE, headers=headers, json={"work_type": "height", "zone_text": "z"})
    wp_id = r.json()["id"]
    await async_client.post(f"{BASE}/{wp_id}/members", headers=headers, json={"person_id": str(person.id), "role": "foreman"})

    # no personal permit yet → readiness not ok, issue 409 WORK_PERMIT_BLOCKED
    rd = await async_client.get(f"{BASE}/{wp_id}/readiness", headers=headers)
    assert rd.status_code == status.HTTP_200_OK and rd.json()["ok"] is False
    blocked = await async_client.post(f"{BASE}/{wp_id}/issue", headers=headers, json={})
    assert blocked.status_code == status.HTTP_409_CONFLICT

    # seed an active personal permit, then issue succeeds
    from datetime import date as _date, timedelta as _td
    from app.domains.permits import service as permit_svc
    async with sessionmaker() as session:
        await permit_svc.create_permit(
            session, tenant_id=person.tenant_id, person_id=person.id, permit_type="height",
            issued_at=_date.today(), valid_until=_date.today() + _td(days=30),
        )
        await session.commit()

    ok = await async_client.post(f"{BASE}/{wp_id}/issue", headers=headers, json={})
    assert ok.status_code == status.HTTP_200_OK, ok.text
    assert ok.json()["status"] == "issued"

    # suspend → resume → close, events recorded
    assert (await async_client.post(f"{BASE}/{wp_id}/suspend", headers=headers, json={})).json()["status"] == "suspended"
    assert (await async_client.post(f"{BASE}/{wp_id}/resume", headers=headers, json={})).json()["status"] == "issued"
    assert (await async_client.post(f"{BASE}/{wp_id}/close", headers=headers, json={})).json()["status"] == "closed"

    ev = await async_client.get(f"{BASE}/{wp_id}/events", headers=headers)
    assert [e["event_type"] for e in ev.json()] == ["issued", "suspended", "resumed", "closed"]


@pytest.mark.asyncio
async def test_close_from_draft_409(async_client, make_auth_headers, data_factory):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    r = await async_client.post(BASE, headers=headers, json={"work_type": "height", "zone_text": "z"})
    wp_id = r.json()["id"]
    bad = await async_client.post(f"{BASE}/{wp_id}/close", headers=headers, json={})
    assert bad.status_code == status.HTTP_409_CONFLICT
