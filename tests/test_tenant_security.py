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
        other = (
            await session.execute(select(Tenant).where(Tenant.slug == "beta"))
        ).scalar_one()

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
async def test_header_can_use_tenant_code_with_slug_scoped_token(
    sessionmaker,
    async_client,
    make_auth_headers,
):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        tenant.code = "TEST-CODE"
        await session.commit()

    headers["x-tenant"] = "TEST-CODE"
    response = await async_client.get("/api/v1/tenants", headers=headers)

    assert response.status_code == 200


@pytest.mark.anyio
async def test_header_can_use_tenant_uuid_with_slug_scoped_token(
    sessionmaker,
    async_client,
    make_auth_headers,
):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        tenant_id = str(tenant.id)

    headers["x-tenant"] = tenant_id
    response = await async_client.get("/api/v1/tenants", headers=headers)

    assert response.status_code == 200
