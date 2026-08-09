"""BIZ-49 срез-6 — API матрицы доступа и «мои клиенты» (разд. 49.3)."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.api.routes import managed_clients as routes
from app.domains.managed_clients.lifecycle import ContractStatus, ManagedClientMode
from app.models.managed_clients import (
    ManagedClient,
    ManagedClientAccess,
    ManagedClientConsent,
)
from app.models.models import AuditLog
from app.schemas.managed_clients import AccessGrantCreate

_NOW = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)
_TENANT = "tenant-1"


def _tenant(tid=_TENANT):
    return SimpleNamespace(id=tid, is_active=True, slug="t1", code="t1")


def _auth(sub="admin-1"):
    return SimpleNamespace(sub=sub, tenant_id=_TENANT, roles=["admin"], company_id=None)


def _request():
    return SimpleNamespace(
        headers={"user-agent": "tests"},
        client=SimpleNamespace(host="127.0.0.1"),
        state=SimpleNamespace(trace_id="trace-1"),
    )


@pytest.fixture(autouse=True)
def _flag_on(monkeypatch):
    monkeypatch.setattr(routes, "is_module_enabled", AsyncMock(return_value=True))


async def _client(session, *, name="Ромашка", tenant_id=_TENANT):
    row = ManagedClient(
        tenant_id=tenant_id,
        name=name,
        mode=ManagedClientMode.LIGHTWEIGHT,
        company_id="comp-a",
        contract_status=ContractStatus.ACTIVE,
    )
    session.add(row)
    await session.flush()
    # Срез-12: без действующего согласия клиента грант не выдаётся.
    session.add(
        ManagedClientConsent(
            tenant_id=tenant_id,
            managed_client_id=row.id,
            document_ref="Поручение №1",
            granted_at=_NOW,
            granted_by_user_id="admin-1",
        )
    )
    await session.flush()
    return row


# --- выдача -----------------------------------------------------------------
@pytest.mark.asyncio
async def test_grant_module_scoped_access(sessionmaker):
    async with sessionmaker() as session:
        c = await _client(session)
        out = await routes.grant_access(
            mcid=c.id,
            payload=AccessGrantCreate(user_id="u1", modules=["documents", "training"]),
            request=_request(),
            tenant=_tenant(),
            session=session,
            access=SimpleNamespace(),
            auth=_auth(),
        )
    assert out.active is True
    assert out.all_modules is False
    assert sorted(out.modules) == ["documents", "training"]
    assert out.granted_by_user_id == "admin-1"


@pytest.mark.asyncio
async def test_empty_grant_is_422(sessionmaker):
    """Ни модулей, ни «весь клиент» — пустышка, молча создавать нельзя."""
    async with sessionmaker() as session:
        c = await _client(session)
        with pytest.raises(HTTPException) as exc:
            await routes.grant_access(
                mcid=c.id,
                payload=AccessGrantCreate(user_id="u1"),
                request=_request(),
                tenant=_tenant(),
                session=session,
                access=SimpleNamespace(),
                auth=_auth(),
            )
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_contradictory_grant_is_422(sessionmaker):
    async with sessionmaker() as session:
        c = await _client(session)
        with pytest.raises(HTTPException) as exc:
            await routes.grant_access(
                mcid=c.id,
                payload=AccessGrantCreate(user_id="u1", all_modules=True, modules=["documents"]),
                request=_request(),
                tenant=_tenant(),
                session=session,
                access=SimpleNamespace(),
                auth=_auth(),
            )
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_duplicate_active_grant_is_409(sessionmaker):
    async with sessionmaker() as session:
        c = await _client(session)
        payload = AccessGrantCreate(user_id="u1", all_modules=True)
        await routes.grant_access(
            mcid=c.id,
            payload=payload,
            request=_request(),
            tenant=_tenant(),
            session=session,
            access=SimpleNamespace(),
            auth=_auth(),
        )
        with pytest.raises(HTTPException) as exc:
            await routes.grant_access(
                mcid=c.id,
                payload=payload,
                request=_request(),
                tenant=_tenant(),
                session=session,
                access=SimpleNamespace(),
                auth=_auth(),
            )
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_grant_is_written_to_audit(sessionmaker):
    """Выдача доступа к чужим данным — событие безопасности, а не правка строки."""
    async with sessionmaker() as session:
        c = await _client(session)
        await routes.grant_access(
            mcid=c.id,
            payload=AccessGrantCreate(user_id="u1", all_modules=True),
            request=_request(),
            tenant=_tenant(),
            session=session,
            access=SimpleNamespace(),
            auth=_auth(),
        )
        await session.flush()
        logs = (
            (
                await session.execute(
                    select(AuditLog).where(AuditLog.action == "managed_client.access.grant")
                )
            )
            .scalars()
            .all()
        )
    assert len(logs) == 1


# --- отзыв ------------------------------------------------------------------
@pytest.mark.asyncio
async def test_revoke_keeps_the_row_as_a_trace(sessionmaker):
    """Отзыв не удаляет строку: иначе «имел ли доступ тогда» не восстановить."""
    async with sessionmaker() as session:
        c = await _client(session)
        granted = await routes.grant_access(
            mcid=c.id,
            payload=AccessGrantCreate(user_id="u1", all_modules=True),
            request=_request(),
            tenant=_tenant(),
            session=session,
            access=SimpleNamespace(),
            auth=_auth(),
        )
        revoked = await routes.revoke_access(
            mcid=c.id,
            grant_id=granted.id,
            request=_request(),
            tenant=_tenant(),
            session=session,
            access=SimpleNamespace(),
            auth=_auth("admin-2"),
        )
        rows = (
            (
                await session.execute(
                    select(ManagedClientAccess).where(ManagedClientAccess.id == granted.id)
                )
            )
            .scalars()
            .all()
        )
    assert revoked.active is False
    assert revoked.revoked_by_user_id == "admin-2"
    assert len(rows) == 1  # строка на месте


@pytest.mark.asyncio
async def test_double_revoke_is_409(sessionmaker):
    async with sessionmaker() as session:
        c = await _client(session)
        granted = await routes.grant_access(
            mcid=c.id,
            payload=AccessGrantCreate(user_id="u1", all_modules=True),
            request=_request(),
            tenant=_tenant(),
            session=session,
            access=SimpleNamespace(),
            auth=_auth(),
        )
        await routes.revoke_access(
            mcid=c.id,
            grant_id=granted.id,
            request=_request(),
            tenant=_tenant(),
            session=session,
            access=SimpleNamespace(),
            auth=_auth(),
        )
        with pytest.raises(HTTPException) as exc:
            await routes.revoke_access(
                mcid=c.id,
                grant_id=granted.id,
                request=_request(),
                tenant=_tenant(),
                session=session,
                access=SimpleNamespace(),
                auth=_auth(),
            )
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_revoked_grant_is_still_listed(sessionmaker):
    """«Кто имел доступ раньше» — такой же вопрос безопасности, как «кто имеет»."""
    async with sessionmaker() as session:
        c = await _client(session)
        granted = await routes.grant_access(
            mcid=c.id,
            payload=AccessGrantCreate(user_id="u1", all_modules=True),
            request=_request(),
            tenant=_tenant(),
            session=session,
            access=SimpleNamespace(),
            auth=_auth(),
        )
        await routes.revoke_access(
            mcid=c.id,
            grant_id=granted.id,
            request=_request(),
            tenant=_tenant(),
            session=session,
            access=SimpleNamespace(),
            auth=_auth(),
        )
        listed = await routes.list_access_grants(
            mcid=c.id, tenant=_tenant(), session=session, access=SimpleNamespace()
        )
    assert len(listed) == 1
    assert listed[0].active is False


# --- «мои клиенты» ----------------------------------------------------------
@pytest.mark.asyncio
async def test_my_clients_only_with_active_grant(sessionmaker):
    async with sessionmaker() as session:
        a = await _client(session, name="Доступен")
        b = await _client(session, name="Отозван")
        await _client(session, name="Без гранта")
        for client in (a, b):
            await routes.grant_access(
                mcid=client.id,
                payload=AccessGrantCreate(user_id="u1", all_modules=True),
                request=_request(),
                tenant=_tenant(),
                session=session,
                access=SimpleNamespace(),
                auth=_auth(),
            )
        grants = (
            (
                await session.execute(
                    select(ManagedClientAccess).where(ManagedClientAccess.managed_client_id == b.id)
                )
            )
            .scalars()
            .all()
        )
        await routes.revoke_access(
            mcid=b.id,
            grant_id=grants[0].id,
            request=_request(),
            tenant=_tenant(),
            session=session,
            access=SimpleNamespace(),
            auth=_auth(),
        )
        await session.commit()

        out = await routes.my_managed_clients(
            tenant=_tenant(), session=session, access=SimpleNamespace(), auth=_auth("u1")
        )
    assert [i.client_name for i in out.items] == ["Доступен"]


@pytest.mark.asyncio
async def test_no_grants_means_empty_not_whole_portfolio(sessionmaker):
    """Отсутствие грантов — это НЕ «доступ ко всему портфелю»."""
    async with sessionmaker() as session:
        await _client(session, name="Чей-то клиент")
        await session.commit()
        out = await routes.my_managed_clients(
            tenant=_tenant(), session=session, access=SimpleNamespace(), auth=_auth("u-без-грантов")
        )
    assert out.items == []


@pytest.mark.asyncio
async def test_my_clients_are_tenant_scoped(sessionmaker):
    async with sessionmaker() as session:
        alien = await _client(session, name="Чужой", tenant_id="tenant-other")
        session.add(
            ManagedClientAccess(
                tenant_id="tenant-other",
                managed_client_id=alien.id,
                user_id="u1",
                all_modules=True,
                modules=[],
                granted_at=_NOW,
            )
        )
        await session.commit()
        out = await routes.my_managed_clients(
            tenant=_tenant(), session=session, access=SimpleNamespace(), auth=_auth("u1")
        )
    assert out.items == []


@pytest.mark.asyncio
async def test_my_clients_respects_feature_flag(sessionmaker, monkeypatch):
    monkeypatch.setattr(routes, "is_module_enabled", AsyncMock(return_value=False))
    async with sessionmaker() as session:
        with pytest.raises(HTTPException) as exc:
            await routes.my_managed_clients(
                tenant=_tenant(), session=session, access=SimpleNamespace(), auth=_auth("u1")
            )
    assert exc.value.status_code == 404
