import pytest
from sqlalchemy import select

from app.models.models import RoleEnum, Tenant


@pytest.mark.anyio
async def test_employee_cannot_list_tenants(async_client, make_auth_headers):
    headers = await make_auth_headers(RoleEnum.EMPLOYEE)
    headers["x-tenant"] = "test"

    response = await async_client.get("/api/v1/tenants", headers=headers)

    assert response.status_code == 403


@pytest.mark.anyio
async def test_cannot_read_other_tenant(sessionmaker, async_client, make_auth_headers):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    headers["x-tenant"] = "test"

    async with sessionmaker() as session:
        other = (await session.execute(select(Tenant).where(Tenant.slug == "beta"))).scalar_one()

    response = await async_client.get(
        f"/api/v1/tenants/{other.id}",
        headers=headers,
    )

    assert response.status_code == 404


@pytest.mark.anyio
async def test_header_token_tenant_mismatch_denied(async_client, make_auth_headers):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    headers["x-tenant"] = "beta"

    response = await async_client.get("/api/v1/tenants", headers=headers)

    assert response.status_code == 403


@pytest.mark.anyio
async def test_cannot_patch_other_tenant_quotas(sessionmaker, async_client, make_auth_headers):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    headers["x-tenant"] = "test"

    async with sessionmaker() as session:
        other = (await session.execute(select(Tenant).where(Tenant.slug == "beta"))).scalar_one()

    response = await async_client.patch(
        f"/api/v1/tenants/{other.id}/quotas",
        headers=headers,
        json={"max_parallel_jobs": 9},
    )

    assert response.status_code == 403
