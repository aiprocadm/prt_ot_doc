"""BIZ-49 срез-7 — вход в контекст клиента и обязательная пометка в аудите."""

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

_NOW = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)
_TENANT = "tenant-1"


def _tenant(tid=_TENANT):
    return SimpleNamespace(id=tid, is_active=True, slug="t1", code="t1")


def _auth(sub="u1"):
    return SimpleNamespace(sub=sub, tenant_id=_TENANT, roles=["ot_specialist"], company_id=None)


def _request(path="/api/v1/managed-clients/x/context", method="POST"):
    return SimpleNamespace(
        headers={"user-agent": "tests"},
        client=SimpleNamespace(host="127.0.0.1"),
        state=SimpleNamespace(trace_id="trace-1"),
        url=SimpleNamespace(path=path),
        method=method,
    )


@pytest.fixture(autouse=True)
def _flag_on(monkeypatch):
    monkeypatch.setattr(routes, "is_feature_enabled", AsyncMock(return_value=True))


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
    # Срез-12: вход «от имени» требует действующего согласия клиента.
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


async def _grant(
    session, *, client_id, user_id="u1", all_modules=True, modules=None, revoked=False
):
    row = ManagedClientAccess(
        tenant_id=_TENANT,
        managed_client_id=client_id,
        user_id=user_id,
        all_modules=all_modules,
        modules=list(modules or []),
        granted_at=_NOW,
        revoked_at=_NOW if revoked else None,
    )
    session.add(row)
    await session.flush()
    return row


@pytest.mark.asyncio
async def test_enter_context_with_active_grant(sessionmaker):
    async with sessionmaker() as session:
        c = await _client(session)
        await _grant(session, client_id=c.id)
        out = await routes.enter_client_context(
            mcid=c.id,
            request=_request(),
            tenant=_tenant(),
            session=session,
            access=SimpleNamespace(),
            auth=_auth(),
        )
    assert out.client_id == c.id
    assert out.client_name == "Ромашка"
    assert out.all_modules is True
    assert out.audit_recorded is True


@pytest.mark.asyncio
async def test_entering_context_is_written_to_audit(sessionmaker):
    """Требование ПДн из ТЗ: кто, от имени какого клиента, что сделал."""
    async with sessionmaker() as session:
        c = await _client(session)
        await _grant(session, client_id=c.id, all_modules=False, modules=["documents"])
        await routes.enter_client_context(
            mcid=c.id,
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
                    select(AuditLog).where(AuditLog.action == "managed_client.context.enter")
                )
            )
            .scalars()
            .all()
        )
    assert len(logs) == 1
    meta = logs[0].details["meta_json"]
    assert meta["actor_user_id"] == "u1"
    assert meta["managed_client_id"] == c.id
    assert meta["managed_client_name"] == "Ромашка"
    assert meta["on_behalf_of_client"] is True
    assert meta["modules"] == ["documents"]


@pytest.mark.asyncio
async def test_no_grant_is_403_not_silent(sessionmaker):
    """Отказ, а не «работай в своём контексте»: иначе человек уверен, что
    пишет в данные клиента, а пишет их не туда."""
    async with sessionmaker() as session:
        c = await _client(session)
        with pytest.raises(HTTPException) as exc:
            await routes.enter_client_context(
                mcid=c.id,
                request=_request(),
                tenant=_tenant(),
                session=session,
                access=SimpleNamespace(),
                auth=_auth(),
            )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_revoked_grant_is_403(sessionmaker):
    async with sessionmaker() as session:
        c = await _client(session)
        await _grant(session, client_id=c.id, revoked=True)
        with pytest.raises(HTTPException) as exc:
            await routes.enter_client_context(
                mcid=c.id,
                request=_request(),
                tenant=_tenant(),
                session=session,
                access=SimpleNamespace(),
                auth=_auth(),
            )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_colleagues_grant_does_not_let_me_in(sessionmaker):
    async with sessionmaker() as session:
        c = await _client(session)
        await _grant(session, client_id=c.id, user_id="u2")
        with pytest.raises(HTTPException) as exc:
            await routes.enter_client_context(
                mcid=c.id,
                request=_request(),
                tenant=_tenant(),
                session=session,
                access=SimpleNamespace(),
                auth=_auth("u1"),
            )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_unknown_client_answers_the_same_403(sessionmaker):
    """Существование чужого клиента — тоже сведения: 403, а не 404."""
    async with sessionmaker() as session:
        with pytest.raises(HTTPException) as exc:
            await routes.enter_client_context(
                mcid="нет-такого",
                request=_request(),
                tenant=_tenant(),
                session=session,
                access=SimpleNamespace(),
                auth=_auth(),
            )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_client_of_another_tenant_is_403(sessionmaker):
    async with sessionmaker() as session:
        alien = await _client(session, name="Чужой", tenant_id="tenant-other")
        with pytest.raises(HTTPException) as exc:
            await routes.enter_client_context(
                mcid=alien.id,
                request=_request(),
                tenant=_tenant(),
                session=session,
                access=SimpleNamespace(),
                auth=_auth(),
            )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_module_scoped_context_returns_its_modules(sessionmaker):
    async with sessionmaker() as session:
        c = await _client(session)
        await _grant(session, client_id=c.id, all_modules=False, modules=["documents", "training"])
        out = await routes.enter_client_context(
            mcid=c.id,
            request=_request(),
            tenant=_tenant(),
            session=session,
            access=SimpleNamespace(),
            auth=_auth(),
        )
    assert out.all_modules is False
    assert sorted(out.modules) == ["documents", "training"]
