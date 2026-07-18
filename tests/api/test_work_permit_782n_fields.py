from __future__ import annotations

import pytest

from app.models.models import RoleEnum

BASE = "/api/v1/work-permits"


@pytest.mark.asyncio
async def test_create_roundtrips_782n_fields(async_client, make_auth_headers):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    body = {
        "work_type": "height",
        "zone_text": "фасад",
        "subdivision_text": "Цех №2",
        "content_text": "монтаж ограждения",
        "safety_systems": ["fall_arrest", "rescue_evacuation"],
        "ppe_text": "каска, привязь",
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


@pytest.mark.asyncio
async def test_create_confined_space_valid_type_specific(async_client, make_auth_headers):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    body = {
        "work_type": "confined_space",
        "zone_text": "резервуар №3",
        "type_specific": {
            "ventilation": "forced",
            "gas_analysis": [{"parameter": "oxygen", "value": "20.9"}],
        },
    }
    r = await async_client.post(BASE, headers=headers, json=body)
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["type_specific"]["ventilation"] == "forced"


@pytest.mark.asyncio
async def test_create_confined_space_invalid_ventilation(async_client, make_auth_headers):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    body = {
        "work_type": "confined_space",
        "zone_text": "резервуар №3",
        "type_specific": {"ventilation": "turbo"},
    }
    r = await async_client.post(BASE, headers=headers, json=body)
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_patch_confined_space_invalid_type_specific(async_client, make_auth_headers):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    # Create a minimal confined_space permit first
    create_body = {"work_type": "confined_space", "zone_text": "шахта"}
    cr = await async_client.post(BASE, headers=headers, json=create_body)
    assert cr.status_code == 201, cr.text
    wp_id = cr.json()["id"]
    # PATCH with invalid type_specific — route should validate against persisted work_type
    r = await async_client.patch(
        f"{BASE}/{wp_id}",
        headers=headers,
        json={"type_specific": {"ventilation": "turbo"}},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_patch_work_type_to_height_clears_stale_type_specific(
    async_client, make_auth_headers
):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    # Confined permit carrying a valid type_specific section.
    create_body = {
        "work_type": "confined_space",
        "zone_text": "колодец",
        "type_specific": {"ventilation": "forced"},
    }
    cr = await async_client.post(BASE, headers=headers, json=create_body)
    assert cr.status_code == 201, cr.text
    wp_id = cr.json()["id"]
    assert cr.json()["type_specific"] == {"ventilation": "forced"}
    # Switching to height (a profile without its own type_specific section) WITHOUT
    # resending type_specific must clear the now-invalid stale section, not keep it.
    r = await async_client.patch(
        f"{BASE}/{wp_id}",
        headers=headers,
        json={"work_type": "height"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["work_type"] == "height"
    assert r.json()["type_specific"] is None
