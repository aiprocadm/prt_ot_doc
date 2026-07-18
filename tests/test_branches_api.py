"""RC-014 contract tests: Branch entity (master data) + Site.branch_id linkage.

Covers the acceptance frame from GAP_REPORT RC-014 / TZ_REFACTOR_AND_RELEASE §REL-4:
CRUD contract for the new ``/api/v1/branches`` endpoints, tenant isolation
(cross-tenant ids → 404, list no-bleed), and the site↔branch link validation
(branch must exist, belong to the same tenant AND the same company — the
``site.branch_id`` column is an app-level reference without a DB FK, so the
API layer is the integrity boundary being pinned here).
"""

from __future__ import annotations

import pytest
from fastapi import status
from httpx import AsyncClient

from app.models.models import RoleEnum
from tests.utils.factories import TestDataFactory


async def _make_company(data_factory: TestDataFactory, sessionmaker, *, name: str, slug=None):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(
            session=session, **({"slug": slug} if slug else {})
        )
        company = await data_factory.create_company(tenant=tenant, name=name, session=session)
        await session.commit()
        return tenant, str(company.id)


def _branch_payload(company_id: str, name: str = "Филиал Казань") -> dict:
    return {
        "company_id": company_id,
        "name": name,
        "code": "KZN-01",
        "address": "Казань, ул. Баумана, 1",
        "contact_name": "Иванов И.И.",
        "contact_phone": "+7-843-000-00-00",
        "contact_email": "kzn@example.com",
    }


@pytest.mark.asyncio
async def test_branch_crud_roundtrip(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    _, company_id = await _make_company(data_factory, sessionmaker, name="BranchCRUD Co")
    headers = await make_auth_headers(RoleEnum.ADMIN)

    created = await async_client.post(
        "/api/v1/branches", json=_branch_payload(company_id), headers=headers
    )
    assert created.status_code == status.HTTP_201_CREATED, created.text
    body = created.json()
    branch_id = body["id"]
    assert body["company_id"] == company_id
    assert body["name"] == "Филиал Казань"
    assert body["status"] == "active"

    listed = await async_client.get(
        "/api/v1/branches", params={"company_id": company_id}, headers=headers
    )
    assert listed.status_code == status.HTTP_200_OK
    assert branch_id in {item["id"] for item in listed.json()["items"]}
    assert "ETag" in listed.headers

    fetched = await async_client.get(f"/api/v1/branches/{branch_id}", headers=headers)
    assert fetched.status_code == status.HTTP_200_OK
    assert fetched.json()["code"] == "KZN-01"

    patched = await async_client.patch(
        f"/api/v1/branches/{branch_id}",
        json={"name": "Филиал Казань-Центр", "status": "archived"},
        headers=headers,
    )
    assert patched.status_code == status.HTTP_200_OK
    assert patched.json()["name"] == "Филиал Казань-Центр"
    assert patched.json()["status"] == "archived"

    deleted = await async_client.delete(f"/api/v1/branches/{branch_id}", headers=headers)
    assert deleted.status_code == status.HTTP_204_NO_CONTENT

    gone = await async_client.get(f"/api/v1/branches/{branch_id}", headers=headers)
    assert gone.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_branch_create_requires_existing_company(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    await _make_company(data_factory, sessionmaker, name="BranchNoCo Co")
    headers = await make_auth_headers(RoleEnum.ADMIN)

    response = await async_client.post(
        "/api/v1/branches",
        json=_branch_payload("00000000-0000-0000-0000-000000000000"),
        headers=headers,
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_branch_cross_tenant_isolation(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    """Чужой branch_id при валидном JWT другого тенанта → 404; список не «протекает»."""
    _, company_a = await _make_company(data_factory, sessionmaker, name="BranchIso A Co")
    await _make_company(data_factory, sessionmaker, name="BranchIso B Co", slug="branch-iso-b")

    headers_a = await make_auth_headers(RoleEnum.ADMIN)
    headers_b = await make_auth_headers(RoleEnum.ADMIN, tenant="branch-iso-b")

    created = await async_client.post(
        "/api/v1/branches",
        json=_branch_payload(company_a, name="Только для A"),
        headers=headers_a,
    )
    assert created.status_code == status.HTTP_201_CREATED, created.text
    branch_id = created.json()["id"]

    assert (
        await async_client.get(f"/api/v1/branches/{branch_id}", headers=headers_b)
    ).status_code == status.HTTP_404_NOT_FOUND
    assert (
        await async_client.patch(
            f"/api/v1/branches/{branch_id}", json={"name": "x"}, headers=headers_b
        )
    ).status_code == status.HTTP_404_NOT_FOUND
    assert (
        await async_client.delete(f"/api/v1/branches/{branch_id}", headers=headers_b)
    ).status_code == status.HTTP_404_NOT_FOUND

    listed_b = await async_client.get("/api/v1/branches", headers=headers_b)
    assert listed_b.status_code == status.HTTP_200_OK
    assert branch_id not in {item["id"] for item in listed_b.json()["items"]}


@pytest.mark.asyncio
async def test_site_links_to_branch_and_echoes_it(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    _, company_id = await _make_company(data_factory, sessionmaker, name="SiteLink Co")
    headers = await make_auth_headers(RoleEnum.ADMIN)

    branch = await async_client.post(
        "/api/v1/branches", json=_branch_payload(company_id), headers=headers
    )
    assert branch.status_code == status.HTTP_201_CREATED, branch.text
    branch_id = branch.json()["id"]

    site = await async_client.post(
        "/api/v1/sites",
        json={"company_id": company_id, "branch_id": branch_id, "name": "Объект при филиале"},
        headers=headers,
    )
    assert site.status_code == status.HTTP_201_CREATED, site.text
    assert site.json()["branch_id"] == branch_id
    site_id = site.json()["id"]

    # Отвязка/перепривязка через PATCH.
    unlinked = await async_client.patch(
        f"/api/v1/sites/{site_id}", json={"branch_id": None}, headers=headers
    )
    assert unlinked.status_code == status.HTTP_200_OK
    assert unlinked.json()["branch_id"] is None

    relinked = await async_client.patch(
        f"/api/v1/sites/{site_id}", json={"branch_id": branch_id}, headers=headers
    )
    assert relinked.status_code == status.HTTP_200_OK
    assert relinked.json()["branch_id"] == branch_id


@pytest.mark.asyncio
async def test_site_branch_company_mismatch_rejected(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    tenant, company_a = await _make_company(data_factory, sessionmaker, name="Mismatch A Co")
    async with sessionmaker() as session:
        company_b = await data_factory.create_company(
            tenant=tenant, name="Mismatch B Co", session=session
        )
        await session.commit()
        company_b_id = str(company_b.id)
    headers = await make_auth_headers(RoleEnum.ADMIN)

    branch_b = await async_client.post(
        "/api/v1/branches",
        json=_branch_payload(company_b_id, name="Филиал B"),
        headers=headers,
    )
    assert branch_b.status_code == status.HTTP_201_CREATED, branch_b.text
    branch_b_id = branch_b.json()["id"]

    # Site компании A с филиалом компании B → 400.
    created = await async_client.post(
        "/api/v1/sites",
        json={"company_id": company_a, "branch_id": branch_b_id, "name": "Чужой филиал"},
        headers=headers,
    )
    assert created.status_code == status.HTTP_400_BAD_REQUEST

    # Несуществующий филиал → 404.
    ghost = await async_client.post(
        "/api/v1/sites",
        json={
            "company_id": company_a,
            "branch_id": "00000000-0000-0000-0000-000000000000",
            "name": "Призрачный филиал",
        },
        headers=headers,
    )
    assert ghost.status_code == status.HTTP_404_NOT_FOUND
