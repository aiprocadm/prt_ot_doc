from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.security import verify_token
from app.models.models import RoleEnum
from tests.utils.factories import TestDataFactory


@pytest.mark.anyio
async def test_login_success(
    async_client: AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
    data_factory: TestDataFactory,
) -> None:
    async with sessionmaker() as session:
        user = await data_factory.create_user(
            email="admin@example.com",
            role=RoleEnum.ADMIN,
            password="secret123",
            session=session,
        )
        tenant_id = user.tenant_id
        await session.commit()
        user_id = user.id

    response = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "secret123"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert "access_token" in payload and "refresh_token" in payload

    access_claims = verify_token(payload["access_token"], expected_type="access")
    refresh_claims = verify_token(payload["refresh_token"], expected_type="refresh")

    assert access_claims["sub"] == user_id
    assert refresh_claims["sub"] == user_id
    assert access_claims["role"] == RoleEnum.ADMIN.value
    assert refresh_claims["role"] == RoleEnum.ADMIN.value
    assert access_claims["tenant"] == "test"
    assert refresh_claims["tenant"] == "test"
    assert access_claims["tenant_id"] == tenant_id
    assert refresh_claims["tenant_id"] == tenant_id


@pytest.mark.anyio
async def test_login_rejects_invalid_password(
    async_client: AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
    data_factory: TestDataFactory,
) -> None:
    async with sessionmaker() as session:
        await data_factory.create_user(
            email="user@example.com",
            role=RoleEnum.EMPLOYEE,
            password="correct-password",
            session=session,
        )
        await session.commit()

    response = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "user@example.com", "password": "wrong-password"},
    )
    assert response.status_code == 401
    body = response.json()
    assert body["code"] == "http_401"
    assert body["message"] == "Invalid email or password"
    assert body["trace_id"]


@pytest.mark.anyio
async def test_login_rejects_unknown_email(async_client: AsyncClient) -> None:
    response = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "missing@example.com", "password": "whatever"},
    )
    assert response.status_code == 401
    body = response.json()
    assert body["code"] == "http_401"
    assert body["message"] == "Invalid email or password"
    assert body["trace_id"]


@pytest.mark.anyio
async def test_login_rejects_tenant_id_field(async_client: AsyncClient) -> None:
    response = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "user@example.com", "password": "secret", "tenant_id": "evil"},
    )
    assert response.status_code == 422
    body = response.json()
    assert body["detail"][0]["type"] == "extra_forbidden"


@pytest.mark.anyio
async def test_refresh_issues_new_token_pair(
    async_client: AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
    data_factory: TestDataFactory,
) -> None:
    async with sessionmaker() as session:
        await data_factory.create_user(
            email="refresh@example.com",
            role=RoleEnum.ADMIN,
            password="refresh-secret",
            session=session,
        )
        await session.commit()

    login_response = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "refresh@example.com", "password": "refresh-secret"},
    )
    assert login_response.status_code == 200
    tokens = login_response.json()

    refresh_response = await async_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert refresh_response.status_code == 200
    new_tokens = refresh_response.json()
    assert new_tokens["access_token"] != tokens["access_token"]
    assert new_tokens["refresh_token"] != tokens["refresh_token"]

    access_claims = verify_token(new_tokens["access_token"], expected_type="access")
    refresh_claims = verify_token(new_tokens["refresh_token"], expected_type="refresh")
    assert access_claims["tenant"] == "test"
    assert refresh_claims["tenant"] == "test"


@pytest.mark.anyio
async def test_company_creation_requires_admin_role(
    async_client: AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
    data_factory: TestDataFactory,
) -> None:
    async with sessionmaker() as session:
        await data_factory.create_user(
            email="manager@example.com",
            role=RoleEnum.EMPLOYEE,
            password="manager-pass",
            session=session,
        )
        await data_factory.create_user(
            email="creator@example.com",
            role=RoleEnum.ADMIN,
            password="creator-pass",
            session=session,
        )
        await session.commit()

    manager_login = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "manager@example.com", "password": "manager-pass"},
    )
    assert manager_login.status_code == 200
    manager_access = manager_login.json()["access_token"]

    blocked = await async_client.get(
        "/api/v1/auth/admin/ping",
        headers={"Authorization": f"Bearer {manager_access}"},
    )
    assert blocked.status_code == 403
    blocked_body = blocked.json()
    assert blocked_body["code"] == "forbidden"
    assert blocked_body["message"] == "Insufficient role"
    assert blocked_body["trace_id"]

    admin_login = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "creator@example.com", "password": "creator-pass"},
    )
    assert admin_login.status_code == 200
    admin_access = admin_login.json()["access_token"]

    ping_response = await async_client.get(
        "/api/v1/auth/admin/ping",
        headers={"Authorization": f"Bearer {admin_access}"},
    )
    assert ping_response.status_code == 200
    body = ping_response.json()
    assert body["status"] == "ok"
    assert isinstance(body["user_id"], str)


@pytest.mark.anyio
async def test_me_permissions_returns_roles_permissions_and_scopes(
    async_client: AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
    data_factory: TestDataFactory,
) -> None:
    async with sessionmaker() as session:
        await data_factory.create_user(
            email="perm@example.com",
            role=RoleEnum.ADMIN,
            password="perm-secret",
            session=session,
        )
        await session.commit()

    login_response = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "perm@example.com", "password": "perm-secret"},
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]

    response = await async_client.get(
        "/api/v1/auth/me/permissions",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload["roles"], list)
    assert isinstance(payload["permissions"], list)
    assert isinstance(payload["abac_scopes"], dict)
