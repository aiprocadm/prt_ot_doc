from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.models import RoleEnum
from app.services.audit import AuditService
from tests.utils.factories import TestDataFactory


@pytest.mark.anyio("asyncio")
async def test_audit_history_orders_latest_first(
    async_client: AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
    data_factory: TestDataFactory,
    make_auth_headers,
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        audit = AuditService(session)
        now = datetime.now(tz=timezone.utc)
        await audit.log_event(
            tenant_id=tenant.id,
            action="created",
            object_type="document",
            object_id="doc-1",
            user_id=None,
            ip="127.0.0.1",
            when=now - timedelta(minutes=5),
        )
        await audit.log_event(
            tenant_id=tenant.id,
            action="updated",
            object_type="document",
            object_id="doc-1",
            user_id=None,
            ip="127.0.0.1",
            when=now,
        )
        await session.commit()

    headers = {**dict(async_client.headers), **await make_auth_headers(RoleEnum.ADMIN)}
    response = await async_client.get(
        "/api/v1/audit",
        params={"object_id": "doc-1"},
        headers=headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 2
    assert payload["items"][0]["action"] == "updated"
    assert payload["items"][1]["action"] == "created"


@pytest.mark.anyio("asyncio")
async def test_audit_history_filters_by_action_and_type(
    async_client: AsyncClient,
    sessionmaker: async_sessionmaker[AsyncSession],
    data_factory: TestDataFactory,
    make_auth_headers,
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        audit = AuditService(session)
        await audit.log_event(
            tenant_id=tenant.id,
            action="created",
            object_type="document",
            object_id="doc-2",
            user_id=None,
            ip="127.0.0.1",
        )
        await audit.log_event(
            tenant_id=tenant.id,
            action="updated",
            object_type="template",
            object_id="doc-2",
            user_id=None,
            ip="127.0.0.1",
        )
        await session.commit()

    headers = {**dict(async_client.headers), **await make_auth_headers(RoleEnum.ADMIN)}
    response = await async_client.get(
        "/api/v1/audit",
        params={"object_id": "doc-2", "object_type": "document", "action": "created"},
        headers=headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["action"] == "created"
    assert payload["items"][0]["object_type"] == "document"


@pytest.mark.anyio("asyncio")
async def test_audit_history_requires_admin(async_client: AsyncClient, make_auth_headers) -> None:
    headers = {**dict(async_client.headers), **await make_auth_headers(RoleEnum.CLIENT_USER)}
    response = await async_client.get(
        "/api/v1/audit",
        params={"object_id": "doc-3"},
        headers=headers,
    )

    assert response.status_code == 403


@pytest.mark.anyio("asyncio")
async def test_audit_history_rejects_blank_object_id(
    async_client: AsyncClient, make_auth_headers
) -> None:
    headers = {**dict(async_client.headers), **await make_auth_headers(RoleEnum.ADMIN)}
    response = await async_client.get(
        "/api/v1/audit",
        params={"object_id": "   "},
        headers=headers,
    )

    assert response.status_code == 400
