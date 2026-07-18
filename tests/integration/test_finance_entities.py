from __future__ import annotations

import pytest

from app.core.security import issue_access_token
from app.models.models import RoleEnum


@pytest.mark.anyio
async def test_finance_crud_and_rbac(async_client, sessionmaker, data_factory, make_auth_headers):
    admin_headers = await make_auth_headers(RoleEnum.ADMIN)
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        await session.commit()

    dept_payload = {"company_id": company.id, "name": "Operations"}
    dept_response = await async_client.post(
        "/api/v1/departments", json=dept_payload, headers=admin_headers
    )
    assert dept_response.status_code == 201
    department_id = dept_response.json()["id"]

    contract_payload = {
        "company_id": company.id,
        "department_id": department_id,
        "title": "Main contract",
        "counterparty_name": "Vendor LLC",
        "status": "active",
    }
    contract_response = await async_client.post(
        "/api/v1/contracts", json=contract_payload, headers=admin_headers
    )
    assert contract_response.status_code == 201
    contract_id = contract_response.json()["id"]

    order_payload = {"contract_id": contract_id, "order_number": "PO-1"}
    order_response = await async_client.post(
        "/api/v1/orders", json=order_payload, headers=admin_headers
    )
    assert order_response.status_code == 201
    order_id = order_response.json()["id"]

    invoice_payload = {"contract_id": contract_id, "order_id": order_id, "invoice_number": "INV-1"}
    invoice_response = await async_client.post(
        "/api/v1/invoices", json=invoice_payload, headers=admin_headers
    )
    assert invoice_response.status_code == 201

    employee_headers = await make_auth_headers(RoleEnum.EMPLOYEE)
    denied = await async_client.post(
        "/api/v1/invoices", json=invoice_payload, headers=employee_headers
    )
    assert denied.status_code == 403


@pytest.mark.anyio
async def test_finance_tenant_isolation(async_client, sessionmaker, data_factory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        await session.commit()
        other_tenant = await data_factory.ensure_tenant(slug="acme", session=session)
        other_user = await data_factory.create_user(
            tenant=other_tenant,
            role=RoleEnum.ADMIN,
            email="acme-admin@example.com",
            session=session,
        )
        await session.commit()

    token = issue_access_token(
        subject=other_user.id,
        tenant=other_tenant.slug,
        role=other_user.role.value,
        additional_claims={"tenant_id": other_tenant.id},
    )
    headers = {"Authorization": f"Bearer {token}", "x-tenant": other_tenant.slug}
    response = await async_client.get(
        f"/api/v1/departments?company_id={company.id}", headers=headers
    )
    assert response.status_code == 200
    assert response.json()["items"] == []
