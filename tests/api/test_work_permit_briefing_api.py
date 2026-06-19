from __future__ import annotations

import pytest
from app.models.models import RoleEnum

BASE = "/api/v1/work-permits"


async def _make_permit(async_client, headers) -> str:
    r = await async_client.post(
        BASE, headers=headers, json={"work_type": "height", "zone_text": "z"}
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.mark.asyncio
async def test_briefing_create_list_patch(async_client, make_auth_headers, data_factory):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    wp_id = await _make_permit(async_client, headers)

    r = await async_client.post(
        f"{BASE}/{wp_id}/briefing",
        headers=headers,
        json={"topics_text": "страховочные системы"},
    )
    assert r.status_code == 201, r.text
    bid = r.json()["id"]
    assert r.json()["work_permit_id"] == wp_id

    lst = await async_client.get(f"{BASE}/{wp_id}/briefing", headers=headers)
    assert lst.status_code == 200
    assert [b["id"] for b in lst.json()] == [bid]

    upd = await async_client.patch(
        f"{BASE}/{wp_id}/briefing/{bid}",
        headers=headers,
        json={"topics_text": "страховка + эвакуация"},
    )
    assert upd.status_code == 200
    assert upd.json()["topics_text"] == "страховка + эвакуация"
