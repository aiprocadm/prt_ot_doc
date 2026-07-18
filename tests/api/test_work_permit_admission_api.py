from __future__ import annotations

import pytest

from app.models.models import RoleEnum

BASE = "/api/v1/work-permits"


async def _issued_permit(async_client, headers) -> str:
    r = await async_client.post(
        BASE, headers=headers, json={"work_type": "height", "zone_text": "z"}
    )
    wp_id = r.json()["id"]
    iss = await async_client.post(f"{BASE}/{wp_id}/issue", headers=headers, json={})
    assert iss.status_code == 200, iss.text
    return wp_id


@pytest.mark.asyncio
async def test_admission_create_list_patch(async_client, make_auth_headers, data_factory):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    wp_id = await _issued_permit(async_client, headers)

    r = await async_client.post(
        f"{BASE}/{wp_id}/admissions",
        headers=headers,
        json={"admission_date": "2026-06-18", "note": "смена 1"},
    )
    assert r.status_code == 201, r.text
    aid = r.json()["id"]
    assert r.json()["work_permit_id"] == wp_id

    lst = await async_client.get(f"{BASE}/{wp_id}/admissions", headers=headers)
    assert lst.status_code == 200
    assert [a["id"] for a in lst.json()] == [aid]

    upd = await async_client.patch(
        f"{BASE}/{wp_id}/admissions/{aid}",
        headers=headers,
        json={"end_at": "2026-06-18T17:00:00+00:00"},
    )
    assert upd.status_code == 200
    from datetime import datetime, timezone

    end_at = datetime.fromisoformat(upd.json()["end_at"])
    assert end_at.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M") == "2026-06-18T17:00"


@pytest.mark.asyncio
async def test_admission_rejected_when_not_issued(async_client, make_auth_headers, data_factory):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    r = await async_client.post(
        BASE, headers=headers, json={"work_type": "height", "zone_text": "z"}
    )
    wp_id = r.json()["id"]  # draft
    a = await async_client.post(
        f"{BASE}/{wp_id}/admissions", headers=headers, json={"admission_date": "2026-06-18"}
    )
    assert a.status_code == 409, a.text


@pytest.mark.asyncio
async def test_admission_patch_rejects_foreign_permit(
    async_client, make_auth_headers, data_factory
):
    """An admission of permit A must not be patchable via permit B's path (same tenant)."""
    headers = await make_auth_headers(RoleEnum.ADMIN)
    wp_a = await _issued_permit(async_client, headers)
    wp_b = await _issued_permit(async_client, headers)

    r = await async_client.post(
        f"{BASE}/{wp_a}/admissions", headers=headers, json={"admission_date": "2026-06-18"}
    )
    aid = r.json()["id"]

    cross = await async_client.patch(
        f"{BASE}/{wp_b}/admissions/{aid}", headers=headers, json={"note": "hijack"}
    )
    assert cross.status_code == 404, cross.text


@pytest.mark.asyncio
async def test_member_add_emits_event_with_meta(async_client, make_auth_headers, data_factory):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    wp_id = await _issued_permit(async_client, headers)
    person = await data_factory.create_person()
    add = await async_client.post(
        f"{BASE}/{wp_id}/members", headers=headers, json={"person_id": person.id, "role": "member"}
    )
    assert add.status_code == 201, add.text
    evs = await async_client.get(f"{BASE}/{wp_id}/events", headers=headers)
    added = [e for e in evs.json() if e["event_type"] == "member_added"]
    assert added and added[0]["meta"]["person_id"] == person.id
