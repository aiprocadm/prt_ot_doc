"""Personal permits CRUD + lifecycle API tests."""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi import status

from app.models.models import RoleEnum

BASE = "/api/v1/permits"


@pytest.mark.asyncio
async def test_permits_crud_extend_revoke(async_client, make_auth_headers, data_factory):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    person = await data_factory.create_person()

    r = await async_client.post(BASE, headers=headers, json={
        "person_id": str(person.id),
        "permit_type": "Работа на высоте",
        "valid_until": (date.today() + timedelta(days=30)).isoformat(),
    })
    assert r.status_code == status.HTTP_201_CREATED, r.text
    permit_id = r.json()["id"]
    assert r.json()["status"] == "active"
    assert r.json()["is_expired"] is False

    r = await async_client.get(BASE, headers=headers, params={"person_id": str(person.id)})
    assert r.status_code == status.HTTP_200_OK
    assert r.json()["total"] >= 1

    r = await async_client.post(f"{BASE}/{permit_id}/extend", headers=headers, json={
        "valid_until": (date.today() + timedelta(days=90)).isoformat(),
    })
    assert r.status_code == status.HTTP_200_OK

    r = await async_client.post(f"{BASE}/{permit_id}/revoke", headers=headers)
    assert r.status_code == status.HTTP_200_OK
    assert r.json()["status"] == "revoked"

    r = await async_client.patch(f"{BASE}/{permit_id}", headers=headers, json={"permit_type": "z"})
    assert r.status_code == status.HTTP_409_CONFLICT


@pytest.mark.asyncio
async def test_create_permit_unknown_person_404(async_client, make_auth_headers, data_factory):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    await data_factory.ensure_tenant(slug="test")
    r = await async_client.post(BASE, headers=headers, json={
        "person_id": "does-not-exist", "permit_type": "x",
    })
    assert r.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_expired_only_filter(async_client, make_auth_headers, data_factory):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    person = await data_factory.create_person()
    await async_client.post(BASE, headers=headers, json={
        "person_id": str(person.id), "permit_type": "old",
        "issued_at": (date.today() - timedelta(days=10)).isoformat(),
        "valid_until": (date.today() - timedelta(days=1)).isoformat(),
    })
    r = await async_client.get(BASE, headers=headers, params={"expired_only": "true"})
    assert r.status_code == status.HTTP_200_OK
    assert all(item["status"] == "expired" for item in r.json()["items"])
