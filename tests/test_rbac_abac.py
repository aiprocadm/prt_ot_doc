import pytest
from httpx import AsyncClient
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.models import RoleEnum, Tenant, User
from app.services.auth import hash_password


@pytest.fixture(autouse=True)
def _force_asyncio_backend(anyio_backend_name: str) -> None:
    if anyio_backend_name != "asyncio":
        pytest.skip("asyncio backend only")


@pytest.mark.anyio("asyncio")
async def test_client_user_cannot_access_managed_resources(
    async_client: AsyncClient, make_auth_headers
) -> None:
    headers = {
        **dict(async_client.headers),
        **await make_auth_headers(RoleEnum.CLIENT_USER),
    }

    response = await async_client.get("/api/v1/companies", headers=headers)
    assert response.status_code == 403
    body = response.json()
    assert body["code"] == "forbidden"
    assert body["message"] == "Insufficient role"


@pytest.mark.anyio("asyncio")
async def test_cross_tenant_write_is_rejected(
    async_client: AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
    make_auth_headers,
) -> None:
    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        existing = (
            await session.execute(select(User).where(User.email == "admin-rbac@example.com"))
        ).scalar_one_or_none()
        if existing is None:
            session.add(
                User(
                    tenant_id=tenant.id,
                    email="admin-rbac@example.com",
                    full_name="RBAC Admin",
                    role=RoleEnum.ADMIN,
                    hashed_password=hash_password("unused"),
                )
            )
            await session.commit()

    auth_headers = await make_auth_headers(RoleEnum.ADMIN, email="admin-rbac@example.com")
    headers = {**dict(async_client.headers), **auth_headers, "x-tenant": "acme"}

    payload = {
        "name": "Forbidden Corp",
        "inn": "999",
        "legal_address": "Elsewhere",
    }
    response = await async_client.post("/api/v1/companies", json=payload, headers=headers)

    assert response.status_code == 403
    body = response.json()
    assert body["code"] == "forbidden"
    assert "tenant" in body["message"].lower()


@pytest.mark.anyio("asyncio")
async def test_cross_tenant_read_is_forbidden(
    async_client: AsyncClient, make_auth_headers
) -> None:
    headers = {**dict(async_client.headers), **await make_auth_headers()}
    headers["x-tenant"] = "acme"

    response = await async_client.get("/api/v1/templates", headers=headers)

    assert response.status_code == 403
    body = response.json()
    assert body["code"] == "forbidden"
    assert "tenant" in body["message"].lower()
