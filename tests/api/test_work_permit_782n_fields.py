from __future__ import annotations

import pytest
from app.models.models import RoleEnum

BASE = "/api/v1/work-permits"


@pytest.mark.asyncio
async def test_create_roundtrips_782n_fields(async_client, make_auth_headers):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    body = {
        "work_type": "height", "zone_text": "фасад",
        "subdivision_text": "Цех №2", "content_text": "монтаж ограждения",
        "safety_systems": ["fall_arrest", "rescue_evacuation"], "ppe_text": "каска, привязь",
    }
    r = await async_client.post(BASE, headers=headers, json=body)
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["subdivision_text"] == "Цех №2"
    assert data["safety_systems"] == ["fall_arrest", "rescue_evacuation"]

    got = await async_client.get(f"{BASE}/{data['id']}", headers=headers)
    assert got.json()["content_text"] == "монтаж ограждения"


@pytest.mark.asyncio
async def test_create_rejects_bad_safety_system(async_client, make_auth_headers):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    r = await async_client.post(
        BASE,
        headers=headers,
        json={"work_type": "height", "zone_text": "z", "safety_systems": ["bogus"]},
    )
    assert r.status_code == 422
