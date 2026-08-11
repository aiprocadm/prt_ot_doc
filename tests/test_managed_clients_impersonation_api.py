"""BIZ-49 срез-10 — срок работы «от имени» и выход из контекста (Доп. №3 63.2)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.api import dependencies_managed_client as deps
from app.api.routes import managed_clients as routes
from app.domains.managed_clients.impersonation import CONTEXT_TTL
from app.domains.managed_clients.lifecycle import ContractStatus, ManagedClientMode
from app.models.managed_clients import (
    ManagedClient,
    ManagedClientAccess,
    ManagedClientContextSession,
)
from app.models.models import Tenant

_SLUG = "test"
_NOW = datetime(2026, 8, 5, 12, 0, tzinfo=timezone.utc)


async def _tenant_id(session) -> str:
    return (await session.execute(select(Tenant).where(Tenant.slug == _SLUG))).scalars().one().id


def _tenant(tid):
    return SimpleNamespace(id=tid, is_active=True, slug=_SLUG, code=_SLUG)


def _auth(sub="u1"):
    return SimpleNamespace(sub=sub, tenant_id=None, roles=["ot_specialist"], company_id=None)


def _access(sub="u1"):
    return SimpleNamespace(to_auth_context=lambda: _auth(sub))


def _request(path="/api/v1/persons"):
    return SimpleNamespace(
        headers={"user-agent": "tests"},
        client=SimpleNamespace(host="127.0.0.1"),
        state=SimpleNamespace(trace_id="trace-1"),
        url=SimpleNamespace(path=path),
    )


@pytest.fixture(autouse=True)
def _flag_on(monkeypatch):
    monkeypatch.setattr(routes, "is_feature_enabled", AsyncMock(return_value=True))


async def _client_with_grant(session, tid, *, user_id="u1"):
    client = ManagedClient(
        tenant_id=tid,
        name="ООО Ромашка",
        mode=ManagedClientMode.LIGHTWEIGHT,
        company_id="co-a",
        contract_status=ContractStatus.ACTIVE,
    )
    session.add(client)
    await session.flush()
    session.add(
        ManagedClientAccess(
            tenant_id=tid,
            managed_client_id=client.id,
            user_id=user_id,
            all_modules=True,
            modules=[],
            granted_at=_NOW,
        )
    )
    await session.flush()
    return client


async def _enter(session, tid, client_id):
    return await routes.enter_client_context(
        mcid=client_id,
        request=_request(),
        tenant=_tenant(tid),
        session=session,
        access=SimpleNamespace(),
        auth=_auth(),
    )


async def _use_context(session, tid, client_id):
    return await deps.require_client_context(
        request=_request(),
        session=session,
        tenant=_tenant(tid),
        access=_access(),
        x_managed_client=client_id,
    )


@pytest.mark.asyncio
async def test_enter_opens_a_session_with_a_deadline(sessionmaker):
    """ТЗ: работа «от имени» истекает, а не длится вечно."""

    async with sessionmaker() as session:
        tid = await _tenant_id(session)
        client = await _client_with_grant(session, tid)

        out = await _enter(session, tid, client.id)

        rows = (
            (
                await session.execute(
                    select(ManagedClientContextSession).where(
                        ManagedClientContextSession.managed_client_id == client.id
                    )
                )
            )
            .scalars()
            .all()
        )

    assert out.expires_at is not None
    assert 0 < out.seconds_left <= CONTEXT_TTL.total_seconds()
    assert len(rows) == 1 and rows[0].ended_at is None


@pytest.mark.asyncio
async def test_header_alone_no_longer_grants_context(sessionmaker):
    """Грант есть, заголовок правильный, но входа не было — контекста нет.

    Иначе срок работы «от имени» обходился бы простой подстановкой заголовка.
    """

    async with sessionmaker() as session:
        tid = await _tenant_id(session)
        client = await _client_with_grant(session, tid)

        with pytest.raises(HTTPException) as exc:
            await _use_context(session, tid, client.id)

    assert exc.value.status_code == 403
    assert exc.value.detail["code"] == "MANAGED_CLIENT_CONTEXT_EXPIRED"


@pytest.mark.asyncio
async def test_context_works_right_after_entering(sessionmaker):
    async with sessionmaker() as session:
        tid = await _tenant_id(session)
        client = await _client_with_grant(session, tid)
        await _enter(session, tid, client.id)

        ctx = await _use_context(session, tid, client.id)

    assert ctx is not None
    assert ctx.client_name == "ООО Ромашка"


@pytest.mark.asyncio
async def test_expired_session_is_refused_with_its_own_code(sessionmaker):
    """Интерфейсу нужно отличать «нет доступа» от «время вышло»."""

    async with sessionmaker() as session:
        tid = await _tenant_id(session)
        client = await _client_with_grant(session, tid)
        await _enter(session, tid, client.id)
        row = (
            await session.execute(select(ManagedClientContextSession))
        ).scalars().one()
        row.started_at = datetime.now(tz=timezone.utc) - CONTEXT_TTL - timedelta(minutes=1)
        await session.flush()

        with pytest.raises(HTTPException) as exc:
            await _use_context(session, tid, client.id)

    assert exc.value.status_code == 403
    assert exc.value.detail["code"] == "MANAGED_CLIENT_CONTEXT_EXPIRED"
    assert "60 минут" in exc.value.detail["message"]


@pytest.mark.asyncio
async def test_leaving_context_closes_the_session_on_the_server(sessionmaker):
    """До среза-10 выход был чисто интерфейсным: баннер исчезал, сервер не знал."""

    async with sessionmaker() as session:
        tid = await _tenant_id(session)
        client = await _client_with_grant(session, tid)
        await _enter(session, tid, client.id)

        await routes.leave_client_context(
            request=_request("/api/v1/managed-clients/context"),
            tenant=_tenant(tid),
            session=session,
            access=SimpleNamespace(),
            auth=_auth(),
        )

        row = (await session.execute(select(ManagedClientContextSession))).scalars().one()
        assert row.ended_at is not None
        assert row.ended_reason == "left"

        with pytest.raises(HTTPException) as exc:
            await _use_context(session, tid, client.id)

    assert exc.value.detail["code"] == "MANAGED_CLIENT_CONTEXT_EXPIRED"


@pytest.mark.asyncio
async def test_leaving_twice_is_not_an_error(sessionmaker):
    """Повторный клик и вкладка со вчерашним состоянием не должны получать отказ."""

    async with sessionmaker() as session:
        tid = await _tenant_id(session)
        client = await _client_with_grant(session, tid)
        await _enter(session, tid, client.id)
        kw = dict(
            request=_request("/api/v1/managed-clients/context"),
            tenant=_tenant(tid),
            session=session,
            access=SimpleNamespace(),
            auth=_auth(),
        )
        await routes.leave_client_context(**kw)
        out = await routes.leave_client_context(**kw)

    assert out.status_code == 204


@pytest.mark.asyncio
async def test_switching_clients_closes_the_previous_session(sessionmaker):
    """Две одновременные работы «от имени» сделали бы журнал невосстановимым."""

    async with sessionmaker() as session:
        tid = await _tenant_id(session)
        first = await _client_with_grant(session, tid)
        second = ManagedClient(
            tenant_id=tid,
            name="АО Одуванчик",
            mode=ManagedClientMode.LIGHTWEIGHT,
            company_id="co-b",
            contract_status=ContractStatus.ACTIVE,
        )
        session.add(second)
        await session.flush()
        session.add(
            ManagedClientAccess(
                tenant_id=tid,
                managed_client_id=second.id,
                user_id="u1",
                all_modules=True,
                modules=[],
                granted_at=_NOW,
            )
        )
        await session.flush()

        await _enter(session, tid, first.id)
        await _enter(session, tid, second.id)

        rows = (
            (await session.execute(select(ManagedClientContextSession))).scalars().all()
        )
        open_rows = [r for r in rows if r.ended_at is None]

        with pytest.raises(HTTPException):
            await _use_context(session, tid, first.id)

    assert len(rows) == 2
    assert len(open_rows) == 1
    assert open_rows[0].managed_client_id == second.id


@pytest.mark.asyncio
async def test_dangerous_action_is_refused_over_http(authenticated_client):
    """Запрет стоит в middleware, поэтому проверяем настоящим запросом.

    Расставленная руками по обработчикам, такая проверка забывается ровно на
    том роуте, где нужнее всего, и промах ничем не проявляется.
    """

    r = await authenticated_client.delete(
        "/api/v1/persons/whatever", headers={"X-Managed-Client": "mc1"}
    )

    assert r.status_code == 403
    body = r.json()
    assert "MANAGED_CLIENT_ACTION_FORBIDDEN" in r.text
    assert "Выйдите из контекста" in r.text
    assert body is not None


@pytest.mark.asyncio
async def test_the_same_action_without_context_is_not_touched(authenticated_client):
    """Обычная работа под своей ролью не должна платить за чужие запреты."""

    r = await authenticated_client.delete("/api/v1/persons/whatever")

    assert r.status_code != 403 or "MANAGED_CLIENT_ACTION_FORBIDDEN" not in r.text


@pytest.mark.asyncio
async def test_leaving_context_is_never_forbidden(authenticated_client):
    """Иначе запрет запирает сам себя: ни удалить, ни выйти."""

    r = await authenticated_client.delete(
        "/api/v1/managed-clients/context", headers={"X-Managed-Client": "mc1"}
    )

    assert "MANAGED_CLIENT_ACTION_FORBIDDEN" not in r.text


def test_exit_route_is_declared_before_the_client_id_route() -> None:
    """Иначе DELETE /managed-clients/context попадёт в удаление клиента с
    идентификатором «context» — выход из контекста молча стал бы удалением."""

    paths = [
        r.path
        for r in routes.router.routes
        if "DELETE" in getattr(r, "methods", set())
    ]
    assert paths.index("/managed-clients/context") < paths.index("/managed-clients/{mcid}")
