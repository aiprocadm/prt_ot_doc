"""SEC-63 срез-18 — несмываемый след работы «от имени клиента» (Доп. №3, 63.2).

ТЗ требует двух вещей, которых не было: пометки «X от имени Y» на КАЖДОМ
действии и журнала доступа, который клиент может запросить. До этого среза
пометка стояла только на отдельном событии входа в контекст: читающий запись
«специалист изменил карточку» не видел рядом ничего.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from app.api import dependencies_managed_client as deps
from app.api.routes import managed_clients as routes
from app.core.request_context import reset_request_scope, set_request_scope
from app.domains.managed_clients.context import ClientContext
from app.domains.managed_clients.lifecycle import ContractStatus, ManagedClientMode
from app.models.managed_clients import (
    ManagedClient,
    ManagedClientAccess,
    ManagedClientConsent,
    ManagedClientContextSession,
)
from app.models.models import AuditLog
from app.services.audit import AuditService

_NOW = datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc)
_TENANT = "tenant-1"


def _tenant(tid=_TENANT):
    return SimpleNamespace(id=tid, is_active=True, slug="t1", code="t1")


def _auth(sub="u1"):
    return SimpleNamespace(sub=sub, tenant_id=_TENANT, roles=["ot_specialist"], company_id=None)


def _request(path="/api/v1/persons", method="GET"):
    return SimpleNamespace(
        headers={"user-agent": "tests"},
        client=SimpleNamespace(host="10.0.0.7"),
        state=SimpleNamespace(trace_id="trace-1"),
        url=SimpleNamespace(path=path),
        method=method,
    )


@pytest.fixture(autouse=True)
def _flag_on(monkeypatch):
    monkeypatch.setattr(routes, "is_module_enabled", AsyncMock(return_value=True))
    monkeypatch.setattr(deps, "is_module_enabled", AsyncMock(return_value=True), raising=False)


async def _client(session, *, name="Ромашка"):
    row = ManagedClient(
        tenant_id=_TENANT,
        name=name,
        mode=ManagedClientMode.LIGHTWEIGHT,
        company_id="comp-a",
        contract_status=ContractStatus.ACTIVE,
    )
    session.add(row)
    await session.flush()
    session.add(
        ManagedClientConsent(
            tenant_id=_TENANT,
            managed_client_id=row.id,
            document_ref="Поручение №1",
            granted_at=_NOW,
            granted_by_user_id="admin-1",
        )
    )
    await session.flush()
    return row


async def _grant_and_session(session, *, client_id, user_id="u1"):
    session.add(
        ManagedClientAccess(
            tenant_id=_TENANT,
            managed_client_id=client_id,
            user_id=user_id,
            all_modules=True,
            modules=[],
            granted_at=_NOW,
        )
    )
    session.add(
        ManagedClientContextSession(
            tenant_id=_TENANT,
            managed_client_id=client_id,
            user_id=user_id,
            started_at=datetime.now(tz=timezone.utc) - timedelta(minutes=1),
        )
    )
    await session.flush()


async def _touch(session, client, *, path="/api/v1/persons", method="GET", user_id="u1"):
    """Одно обращение к данным клиента через настоящую зависимость."""

    return await deps.require_client_context(
        request=_request(path=path, method=method),
        session=session,
        tenant=_tenant(),
        access=SimpleNamespace(to_auth_context=lambda: _auth(user_id)),
        x_managed_client=client.id,
    )


@pytest.mark.asyncio
async def test_access_log_shows_who_touched_client_data(sessionmaker):
    async with sessionmaker() as session:
        client = await _client(session)
        await _grant_and_session(session, client_id=client.id)
        await _touch(session, client, path="/api/v1/persons", method="GET")
        await _touch(session, client, path="/api/v1/documents", method="POST")

        page = await routes.client_access_log(
            mcid=client.id,
            tenant=_tenant(),
            session=session,
            access=SimpleNamespace(),
        )

        assert page.total == 2
        # Свежие сверху: журнал читают, чтобы увидеть последнее обращение.
        assert [item.path for item in page.items] == [
            "/api/v1/documents",
            "/api/v1/persons",
        ]
        # Метод отвечает на вопрос «читали или правили».
        assert [item.method for item in page.items] == ["POST", "GET"]
        assert {item.actor_user_id for item in page.items} == {"u1"}
        assert page.items[0].ip == "10.0.0.7"


@pytest.mark.asyncio
async def test_access_log_does_not_leak_other_clients(sessionmaker):
    async with sessionmaker() as session:
        mine = await _client(session, name="Ромашка")
        other = await _client(session, name="Одуванчик")
        await _grant_and_session(session, client_id=mine.id)
        await _grant_and_session(session, client_id=other.id)
        await _touch(session, mine, path="/api/v1/persons")
        await _touch(session, other, path="/api/v1/persons")

        page = await routes.client_access_log(
            mcid=mine.id, tenant=_tenant(), session=session, access=SimpleNamespace()
        )
        assert page.total == 1


@pytest.mark.asyncio
async def test_access_log_window_filters_by_time(sessionmaker):
    async with sessionmaker() as session:
        client = await _client(session)
        await _grant_and_session(session, client_id=client.id)
        await _touch(session, client)

        now = datetime.now(tz=timezone.utc)
        # Обе границы: окно «с завтрашнего дня» должно быть пустым, а окно
        # «со вчерашнего» — непустым. Одной проверки мало: сравнение времени,
        # сломанное в обе стороны, дало бы ноль и выглядело бы «правильно».
        after = await routes.client_access_log(
            mcid=client.id,
            tenant=_tenant(),
            session=session,
            access=SimpleNamespace(),
            since=now + timedelta(days=1),
        )
        assert after.total == 0
        assert after.items == []

        around = await routes.client_access_log(
            mcid=client.id,
            tenant=_tenant(),
            session=session,
            access=SimpleNamespace(),
            since=now - timedelta(days=1),
            until=now + timedelta(days=1),
        )
        assert around.total == 1


def _scope_with_context(context: ClientContext | None):
    state = {} if context is None else {"managed_client_context": context}
    return {"type": "http", "state": state}


_CONTEXT = ClientContext(
    user_id="u1",
    client_id="mc-1",
    client_name="Ромашка",
    all_modules=True,
    modules=(),
)


@pytest.mark.asyncio
async def test_every_audit_record_carries_on_behalf_of_mark(sessionmaker):
    """Пометка «X от имени Y» появляется на ЛЮБОЙ записи, а не на входе."""

    async with sessionmaker() as session:
        token = set_request_scope(_scope_with_context(_CONTEXT))
        try:
            row = await AuditService(session).log_event(
                tenant_id=_TENANT,
                action="update",
                object_type="person",
                object_id="p-1",
                user_id="u1",
                ip="10.0.0.7",
                details={"meta_json": {"field": "last_name"}},
            )
        finally:
            reset_request_scope(token)

        assert row.details["on_behalf_of"] == {
            "actor_user_id": "u1",
            "managed_client_id": "mc-1",
            "managed_client_name": "Ромашка",
        }
        # Пометка входит в подписанную часть записи: аудит хэш-сцеплен, и
        # «отвязать» действие от клиента задним числом уже нельзя.
        report = await AuditService(session).verify_audit_chain()
        assert report["ok"] is True


@pytest.mark.asyncio
async def test_mark_cannot_be_forged_without_context(sessionmaker):
    """Вызывающий код не может приписать действие клиенту сам."""

    async with sessionmaker() as session:
        token = set_request_scope(_scope_with_context(None))
        try:
            row = await AuditService(session).log_event(
                tenant_id=_TENANT,
                action="update",
                object_type="person",
                object_id="p-2",
                user_id="u1",
                ip="10.0.0.7",
                details={"on_behalf_of": {"managed_client_id": "чужой-клиент"}},
            )
        finally:
            reset_request_scope(token)

        assert "on_behalf_of" not in row.details


def _asgi_scope(path="/api/v1/persons", method="GET"):
    """Настоящий ASGI-scope: ``request.state`` и контекст запроса — один и тот
    же словарь, а на этом и держится пометка."""

    return {
        "type": "http",
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "server": ("testserver", 80),
        "client": ("10.0.0.7", 5555),
        "headers": [(b"user-agent", b"tests")],
        "state": {"trace_id": "trace-1"},
    }


@pytest.mark.asyncio
async def test_context_enter_record_is_marked_too(sessionmaker):
    """Событие входа тоже помечено — контекст кладётся в состояние ДО записи.

    Порядок здесь не косметика: запиши след раньше, и первая же строка журнала
    окажется единственной непомеченной.
    """

    from starlette.requests import Request

    async with sessionmaker() as session:
        client = await _client(session)
        await _grant_and_session(session, client_id=client.id)
        scope = _asgi_scope()
        token = set_request_scope(scope)
        try:
            await deps.require_client_context(
                request=Request(scope),
                session=session,
                tenant=_tenant(),
                access=SimpleNamespace(to_auth_context=lambda: _auth("u1")),
                x_managed_client=client.id,
            )
        finally:
            reset_request_scope(token)

        row = (
            await session.execute(
                select(AuditLog).where(AuditLog.action == "managed_client.context.enter")
            )
        ).scalar_one()
        assert row.details["on_behalf_of"]["managed_client_id"] == client.id
        assert row.details["meta_json"]["method"] == "GET"
