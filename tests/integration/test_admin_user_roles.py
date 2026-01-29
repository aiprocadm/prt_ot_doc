from __future__ import annotations

import uuid

import pytest

from app.core.security import issue_access_token
from app.models.models import RoleEnum


@pytest.mark.anyio
async def test_admin_can_assign_roles(async_client, sessionmaker, data_factory, make_auth_headers):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        user = await data_factory.create_user(
            tenant=tenant,
            role=RoleEnum.EMPLOYEE,
            email="employee@example.com",
            session=session,
        )

    payload = {"roles": ["accountant", "line_manager"]}
    response = await async_client.post(
        f"/api/v1/admin/users/{user.id}/roles", json=payload, headers=headers
    )
    assert response.status_code == 200
    body = response.json()
    assert set(body["roles"]) >= {"accountant", "line_manager"}


@pytest.mark.anyio
async def test_non_admin_cannot_assign_roles(async_client, make_auth_headers):
    headers = await make_auth_headers(RoleEnum.EMPLOYEE)
    response = await async_client.post(
        f"/api/v1/admin/users/{uuid.uuid4()}/roles",
        json={"roles": ["accountant"]},
        headers=headers,
    )
    assert response.status_code == 403


@pytest.mark.anyio
async def test_assigned_roles_grant_access(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        user = await data_factory.create_user(
            tenant=tenant,
            role=RoleEnum.EMPLOYEE,
            email="finance-user@example.com",
            session=session,
        )
        user.company_id = company.id
        session.add(user)
        await session.flush()
        access_token = issue_access_token(
            subject=user.id,
            tenant=tenant.slug,
            role=user.role.value,
            additional_claims={"tenant_id": tenant.id},
        )
        await session.commit()

    admin_headers = await make_auth_headers(RoleEnum.ADMIN)
    assign_response = await async_client.post(
        f"/api/v1/admin/users/{user.id}/roles",
        json={"roles": ["accountant"]},
        headers=admin_headers,
    )
    assert assign_response.status_code == 200

    headers = {"Authorization": f"Bearer {access_token}", "x-tenant": tenant.slug}
    invoice_payload = {
        "contract_id": "missing",
        "invoice_number": "INV-1",
    }
    response = await async_client.post("/api/v1/invoices", json=invoice_payload, headers=headers)
    assert response.status_code in {400, 404}
