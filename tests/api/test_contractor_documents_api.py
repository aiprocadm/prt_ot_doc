# tests/api/test_contractor_documents_api.py
"""Contractor document registry CRUD + isolation + feature-gate."""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi import status
from httpx import AsyncClient

from app.models.models import RoleEnum
from app.modules.contractors.models import ContractorEmployee, ContractorRegistry

TODAY = date.today()


async def _seed_contractor(sessionmaker, data_factory) -> tuple[str, str]:
    """Return (contractor_id, employee_id) in the default tenant."""
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        contractor = ContractorRegistry(tenant_id=str(tenant.id), name="Doc Contractor")
        session.add(contractor)
        await session.flush()
        emp = ContractorEmployee(
            tenant_id=str(tenant.id), contractor_id=str(contractor.id), full_name="Doc Worker",
        )
        session.add(emp)
        await session.commit()
        return str(contractor.id), str(emp.id)


@pytest.mark.asyncio
async def test_create_and_get_document(async_client: AsyncClient, sessionmaker, data_factory, make_auth_headers):
    contractor_id, _emp = await _seed_contractor(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)

    resp = await async_client.post(
        "/api/v1/contractors/documents",
        headers=headers,
        json={
            "contractor_id": contractor_id,
            "doc_type": "license",
            "title": "СРО допуск",
            "valid_until": (TODAY + timedelta(days=90)).isoformat(),
        },
    )
    assert resp.status_code == status.HTTP_201_CREATED, resp.text
    doc_id = resp.json()["id"]

    got = await async_client.get(f"/api/v1/contractors/documents/{doc_id}", headers=headers)
    assert got.status_code == status.HTTP_200_OK, got.text
    body = got.json()
    assert body["doc_type"] == "license"
    assert body["expiry_status"] == "ok"


@pytest.mark.asyncio
async def test_metadata_only_document_without_file(async_client, sessionmaker, data_factory, make_auth_headers):
    contractor_id, _emp = await _seed_contractor(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)
    resp = await async_client.post(
        "/api/v1/contractors/documents",
        headers=headers,
        json={"contractor_id": contractor_id, "doc_type": "other", "title": "Без файла"},
    )
    assert resp.status_code == status.HTTP_201_CREATED, resp.text
    assert resp.json()["file_id"] is None
    assert resp.json()["expiry_status"] == "ok"  # no valid_until → ok


@pytest.mark.asyncio
async def test_invalid_doc_type_returns_422(async_client, sessionmaker, data_factory, make_auth_headers):
    contractor_id, _emp = await _seed_contractor(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)
    resp = await async_client.post(
        "/api/v1/contractors/documents",
        headers=headers,
        json={"contractor_id": contractor_id, "doc_type": "bogus", "title": "x"},
    )
    assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY, resp.text


@pytest.mark.asyncio
async def test_employee_mismatch_returns_422(async_client, sessionmaker, data_factory, make_auth_headers):
    contractor_id, _emp = await _seed_contractor(sessionmaker, data_factory)
    _other_contractor, other_emp = await _seed_contractor(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)
    resp = await async_client.post(
        "/api/v1/contractors/documents",
        headers=headers,
        json={"contractor_id": contractor_id, "employee_id": other_emp, "doc_type": "medical_cert", "title": "x"},
    )
    assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY, resp.text


@pytest.mark.asyncio
async def test_list_filters_by_contractor(async_client, sessionmaker, data_factory, make_auth_headers):
    contractor_id, _emp = await _seed_contractor(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)
    await async_client.post(
        "/api/v1/contractors/documents", headers=headers,
        json={"contractor_id": contractor_id, "doc_type": "sro", "title": "A"},
    )
    resp = await async_client.get(
        f"/api/v1/contractors/documents?contractor_id={contractor_id}", headers=headers,
    )
    assert resp.status_code == status.HTTP_200_OK, resp.text
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["expiry_status"] == "ok"


@pytest.mark.asyncio
async def test_patch_and_soft_delete(async_client, sessionmaker, data_factory, make_auth_headers):
    contractor_id, _emp = await _seed_contractor(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)
    created = await async_client.post(
        "/api/v1/contractors/documents", headers=headers,
        json={"contractor_id": contractor_id, "doc_type": "license", "title": "Old"},
    )
    doc_id = created.json()["id"]

    patched = await async_client.patch(
        f"/api/v1/contractors/documents/{doc_id}", headers=headers, json={"title": "New"},
    )
    assert patched.status_code == status.HTTP_200_OK, patched.text
    assert patched.json()["title"] == "New"

    deleted = await async_client.delete(f"/api/v1/contractors/documents/{doc_id}", headers=headers)
    assert deleted.status_code == status.HTTP_204_NO_CONTENT
    gone = await async_client.get(f"/api/v1/contractors/documents/{doc_id}", headers=headers)
    assert gone.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_expiring_endpoint_flags_due_soon_and_overdue(async_client, sessionmaker, data_factory, make_auth_headers):
    contractor_id, _emp = await _seed_contractor(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)

    async def _mk(title, days):
        return await async_client.post(
            "/api/v1/contractors/documents", headers=headers,
            json={
                "contractor_id": contractor_id, "doc_type": "training_cert", "title": title,
                "valid_until": (TODAY + timedelta(days=days)).isoformat(),
            },
        )

    await _mk("Future", 90)     # OK — excluded
    await _mk("Soon", 10)       # DUE_SOON — included
    await _mk("Past", -5)       # OVERDUE — included
    await async_client.post(
        "/api/v1/contractors/documents", headers=headers,
        json={"contractor_id": contractor_id, "doc_type": "other", "title": "Open"},
    )

    resp = await async_client.get(
        f"/api/v1/contractors/documents/expiring?contractor_id={contractor_id}", headers=headers,
    )
    assert resp.status_code == status.HTTP_200_OK, resp.text
    body = resp.json()
    assert body["total"] == 2
    titles = {item["title"] for item in body["items"]}
    assert titles == {"Soon", "Past"}
