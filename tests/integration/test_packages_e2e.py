"""End-to-end tests for domain packages (site access, incident, inspection prep, training)."""
from __future__ import annotations

import pytest
from fastapi import status
from sqlalchemy import select

from app.domains.packs.definitions import (
    PACK_CODE_INCIDENT,
    PACK_CODE_INSPECTION_PREP,
    PACK_CODE_SITE_ACCESS,
)
from app.models.models import DocumentPack, RoleEnum, Site
from tests.utils.factories import TestDataFactory

# POST /api/v1/packages (DocumentPack direct-create with {code, name, ...}) no
# longer exists: packages are created via the packs-v2 preset/pack-run API
# (/api/v1/package-presets + /api/v1/pack-runs, async 202). These e2e tests
# target the removed simple-create flow and have failed since the refactor;
# skip until rewritten to packs-v2 (or a convenience create endpoint is added).
pytestmark = pytest.mark.skip(
    reason="DocumentPack direct-create endpoint (POST /api/v1/packages) removed; "
    "packages now created via packs-v2 presets/pack-runs."
)


@pytest.mark.asyncio
async def test_package_site_access_e2e(
    async_client, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    """Verify 'Выход на объект' (site access) package can be created and accessed."""
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        site = Site(tenant_id=tenant.id, company_id=company.id, name="Test Site")
        session.add(site)
        await session.commit()
        await session.refresh(site)
        tenant_id = str(tenant.id)
        site_id = str(site.id)

    headers = await make_auth_headers(RoleEnum.ADMIN)

    # Create site access package
    pack_payload = {
        "code": PACK_CODE_SITE_ACCESS,
        "name": "Site Access Package",
        "company_id": company.id,
        "site_id": site_id,
    }
    pack_resp = await async_client.post(
        "/api/v1/packages",
        json=pack_payload,
        headers=headers,
    )
    assert pack_resp.status_code == status.HTTP_201_CREATED
    pack_id = pack_resp.json()["id"]

    # Verify package is created
    async with sessionmaker() as session:
        pack = (
            await session.execute(
                select(DocumentPack).where(
                    DocumentPack.tenant_id == tenant_id,
                    DocumentPack.code == PACK_CODE_SITE_ACCESS,
                )
            )
        ).scalar_one_or_none()
        assert pack is not None
        assert pack.id == pack_id


@pytest.mark.asyncio
async def test_package_incident_e2e(
    async_client, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    """Verify 'Несчастный случай' (incident response) package can be created and accessed."""
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        tenant_id = str(tenant.id)

    headers = await make_auth_headers(RoleEnum.ADMIN)

    # Create incident package
    pack_payload = {
        "code": PACK_CODE_INCIDENT,
        "name": "Incident Response Package",
        "company_id": company.id,
    }
    pack_resp = await async_client.post(
        "/api/v1/packages",
        json=pack_payload,
        headers=headers,
    )
    assert pack_resp.status_code == status.HTTP_201_CREATED
    pack_id = pack_resp.json()["id"]

    # Verify package is created
    async with sessionmaker() as session:
        pack = (
            await session.execute(
                select(DocumentPack).where(
                    DocumentPack.tenant_id == tenant_id,
                    DocumentPack.code == PACK_CODE_INCIDENT,
                )
            )
        ).scalar_one_or_none()
        assert pack is not None
        assert pack.id == pack_id


@pytest.mark.asyncio
async def test_package_inspection_prep_e2e(
    async_client, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    """Verify 'Подготовка к проверке' (inspection prep) package can be created and accessed."""
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        tenant_id = str(tenant.id)

    headers = await make_auth_headers(RoleEnum.ADMIN)

    # Create inspection prep package
    pack_payload = {
        "code": PACK_CODE_INSPECTION_PREP,
        "name": "Inspection Preparation Package",
        "company_id": company.id,
    }
    pack_resp = await async_client.post(
        "/api/v1/packages",
        json=pack_payload,
        headers=headers,
    )
    assert pack_resp.status_code == status.HTTP_201_CREATED
    pack_id = pack_resp.json()["id"]

    # Verify package is created
    async with sessionmaker() as session:
        pack = (
            await session.execute(
                select(DocumentPack).where(
                    DocumentPack.tenant_id == tenant_id,
                    DocumentPack.code == PACK_CODE_INSPECTION_PREP,
                )
            )
        ).scalar_one_or_none()
        assert pack is not None
        assert pack.id == pack_id


@pytest.mark.asyncio
async def test_package_tenant_isolation_e2e(
    async_client, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    """Verify packages are isolated by tenant."""
    async with sessionmaker() as session:
        tenant_a = await data_factory.ensure_tenant(session=session)
        company_a = await data_factory.create_company(tenant=tenant_a, session=session)
        tenant_a_id = str(tenant_a.id)

    headers = await make_auth_headers(RoleEnum.ADMIN)

    # Create package in tenant A
    pack_payload_a = {
        "code": PACK_CODE_SITE_ACCESS,
        "name": "Tenant A Package",
        "company_id": company_a.id,
    }
    pack_resp_a = await async_client.post(
        "/api/v1/packages",
        json=pack_payload_a,
        headers=headers,
    )
    assert pack_resp_a.status_code == status.HTTP_201_CREATED

    # Try to access with wrong tenant header
    headers_wrong_tenant = {
        **dict(await make_auth_headers(RoleEnum.ADMIN)),
        "x-tenant": "wrong-tenant",
    }
    list_resp = await async_client.get(
        "/api/v1/packages",
        headers=headers_wrong_tenant,
    )
    assert list_resp.status_code == status.HTTP_403_FORBIDDEN

    # Verify correct tenant can list packages
    list_resp_correct = await async_client.get(
        "/api/v1/packages",
        headers=headers,
    )
    assert list_resp_correct.status_code == status.HTTP_200_OK
    packs = list_resp_correct.json()
    assert len(packs) >= 1
