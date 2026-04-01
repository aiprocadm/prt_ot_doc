from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.models import RoleEnum
from tests.utils.factories import TestDataFactory


@pytest.mark.anyio
async def test_auth_me_accepts_token_tenant_without_header(
    app_fixture,
    sessionmaker: async_sessionmaker[AsyncSession],
    data_factory: TestDataFactory,
) -> None:
    async with sessionmaker() as session:
        await data_factory.create_user(
            email="tenant-header@example.com",
            role=RoleEnum.ADMIN,
            password="secret123",
            session=session,
        )
        await session.commit()

    transport = ASGITransport(app=app_fixture)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        login = await client.post(
            "/api/v1/auth/login",
            headers={"X-Tenant": "test"},
            json={"email": "tenant-header@example.com", "password": "secret123"},
        )
        assert login.status_code == 200
        token = login.json()["access_token"]

        missing_header = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert missing_header.status_code == 200
    payload = missing_header.json()
    assert payload["email"] == "tenant-header@example.com"


@pytest.mark.anyio
async def test_auth_refresh_accepts_token_tenant_without_header(
    app_fixture,
    sessionmaker: async_sessionmaker[AsyncSession],
    data_factory: TestDataFactory,
) -> None:
    async with sessionmaker() as session:
        await data_factory.create_user(
            email="refresh-tenant-header@example.com",
            role=RoleEnum.ADMIN,
            password="refresh-secret",
            session=session,
        )
        await session.commit()

    transport = ASGITransport(app=app_fixture)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        login = await client.post(
            "/api/v1/auth/login",
            headers={"X-Tenant": "test"},
            json={"email": "refresh-tenant-header@example.com", "password": "refresh-secret"},
        )
        assert login.status_code == 200
        refresh_token = login.cookies["prt_refresh_token"]

        missing_header = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token},
        )

    assert missing_header.status_code == 200
    payload = missing_header.json()
    assert "access_token" in payload
    assert "prt_refresh_token" in missing_header.cookies


@pytest.mark.anyio
async def test_auth_login_requires_tenant_header_or_domain_context(
    app_fixture,
    sessionmaker: async_sessionmaker[AsyncSession],
    data_factory: TestDataFactory,
) -> None:
    async with sessionmaker() as session:
        await data_factory.create_user(
            email="public-login@example.com",
            role=RoleEnum.ADMIN,
            password="public-secret",
            session=session,
        )
        await session.commit()

    transport = ASGITransport(app=app_fixture)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        login = await client.post(
            "/api/v1/auth/login",
            json={"email": "public-login@example.com", "password": "public-secret"},
        )

    assert login.status_code == 400
