"""BIZ-49 срез-1 — API портфеля ведомых клиентов (разд. 49.1–49.2).

Direct-handler style как у committees: реальная SQLite-сессия, флаг замокан
включённым, tenant — SimpleNamespace.
"""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException, Response
from pydantic import ValidationError

from app.api.routes import managed_clients as routes
from app.domains.managed_clients.lifecycle import ContractStatus, ManagedClientMode
from app.models.managed_clients import ManagedClient
from app.schemas.managed_clients import (
    ManagedClientCreate,
    ManagedClientUpdate,
)

_TODAY = date(2026, 8, 4)


def _tenant(tid="tenant-1"):
    return SimpleNamespace(id=tid, is_active=True, slug="t1", code="t1")


@pytest.fixture(autouse=True)
def _flag_on(monkeypatch):
    monkeypatch.setattr(routes, "is_feature_enabled", AsyncMock(return_value=True))


async def _seed(session, tenant_id="tenant-1", **over):
    payload = dict(
        tenant_id=tenant_id,
        name="ООО Ромашка",
        mode=ManagedClientMode.LIGHTWEIGHT,
        company_id="c1",
        contract_status=ContractStatus.ACTIVE,
    )
    payload.update(over)
    row = ManagedClient(**payload)
    session.add(row)
    await session.flush()
    return row


# --- создание и инварианты режима ------------------------------------------
@pytest.mark.asyncio
async def test_create_lightweight_client(sessionmaker):
    async with sessionmaker() as session:
        out = await routes.create_managed_client(
            payload=ManagedClientCreate(
                name="ООО Ромашка", mode=ManagedClientMode.LIGHTWEIGHT, company_id="c1"
            ),
            tenant=_tenant(),
            session=session,
            access=SimpleNamespace(),
        )
    assert out.mode is ManagedClientMode.LIGHTWEIGHT
    assert out.contract_status is ContractStatus.DRAFT  # договор начинается черновиком


@pytest.mark.asyncio
async def test_create_lightweight_without_company_is_422(sessionmaker):
    async with sessionmaker() as session:
        with pytest.raises(HTTPException) as exc:
            await routes.create_managed_client(
                payload=ManagedClientCreate(
                    name="Без организации", mode=ManagedClientMode.LIGHTWEIGHT
                ),
                tenant=_tenant(),
                session=session,
                access=SimpleNamespace(),
            )
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_create_dedicated_requires_tenant_slug(sessionmaker):
    async with sessionmaker() as session:
        with pytest.raises(HTTPException) as exc:
            await routes.create_managed_client(
                payload=ManagedClientCreate(name="Крупный", mode=ManagedClientMode.DEDICATED),
                tenant=_tenant(),
                session=session,
                access=SimpleNamespace(),
            )
        assert exc.value.status_code == 422
        ok = await routes.create_managed_client(
            payload=ManagedClientCreate(
                name="Крупный",
                mode=ManagedClientMode.DEDICATED,
                dedicated_tenant_slug="client-a",
            ),
            tenant=_tenant(),
            session=session,
            access=SimpleNamespace(),
        )
    assert ok.dedicated_tenant_slug == "client-a"


@pytest.mark.asyncio
async def test_duplicate_name_within_tenant_is_409(sessionmaker):
    async with sessionmaker() as session:
        await _seed(session, name="ООО Ромашка")
        with pytest.raises(HTTPException) as exc:
            await routes.create_managed_client(
                payload=ManagedClientCreate(
                    name="ООО Ромашка", mode=ManagedClientMode.LIGHTWEIGHT, company_id="c2"
                ),
                tenant=_tenant(),
                session=session,
                access=SimpleNamespace(),
            )
    assert exc.value.status_code == 409


# --- договор ----------------------------------------------------------------
@pytest.mark.asyncio
async def test_contract_transition_enforced(sessionmaker):
    async with sessionmaker() as session:
        row = await _seed(session, contract_status=ContractStatus.TERMINATED)
        with pytest.raises(HTTPException) as exc:
            await routes.update_managed_client(
                mcid=row.id,
                payload=ManagedClientUpdate(contract_status=ContractStatus.ACTIVE),
                tenant=_tenant(),
                session=session,
                access=SimpleNamespace(),
            )
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_update_keeps_mode_invariants(sessionmaker):
    """Смена режима без нужной привязки не проходит — иначе строка «повисает»."""
    async with sessionmaker() as session:
        row = await _seed(session)
        with pytest.raises(HTTPException) as exc:
            await routes.update_managed_client(
                mcid=row.id,
                payload=ManagedClientUpdate(mode=ManagedClientMode.DEDICATED),
                tenant=_tenant(),
                session=session,
                access=SimpleNamespace(),
            )
        assert exc.value.status_code == 422
        ok = await routes.update_managed_client(
            mcid=row.id,
            payload=ManagedClientUpdate(
                mode=ManagedClientMode.DEDICATED, dedicated_tenant_slug="client-a"
            ),
            tenant=_tenant(),
            session=session,
            access=SimpleNamespace(),
        )
    assert ok.mode is ManagedClientMode.DEDICATED


def test_schema_rejects_blank_name():
    with pytest.raises(ValidationError):
        ManagedClientCreate(name="   ", mode=ManagedClientMode.LIGHTWEIGHT, company_id="c1")


# --- портфель ---------------------------------------------------------------
@pytest.mark.asyncio
async def test_portfolio_summary_counts_and_signals(sessionmaker, monkeypatch):
    monkeypatch.setattr(routes, "_today", lambda: _TODAY)
    async with sessionmaker() as session:
        await _seed(session, name="Активный", contract_ends_at=_TODAY + timedelta(days=200))
        await _seed(
            session,
            name="Истекает",
            contract_ends_at=_TODAY + timedelta(days=5),
        )
        await _seed(session, name="Черновик", contract_status=ContractStatus.DRAFT)
        await _seed(
            session,
            name="Расторгнут",
            contract_status=ContractStatus.TERMINATED,
            contract_ends_at=_TODAY + timedelta(days=3),
        )
        await _seed(
            session,
            name="Свой контур",
            mode=ManagedClientMode.DEDICATED,
            company_id=None,
            dedicated_tenant_slug="client-a",
        )
        await session.commit()

        out = await routes.portfolio(
            request=SimpleNamespace(headers={}),
            response=Response(),
            tenant=_tenant(),
            session=session,
            access=SimpleNamespace(),
            limit=50,
            offset=0,
        )
    assert out.total == 5
    assert out.summary.active == 3  # два «активных» + dedicated активный
    assert out.summary.draft == 1
    assert out.summary.terminated == 1
    assert out.summary.dedicated == 1
    # расторгнутый со скорым сроком в сигнал НЕ попадает
    assert out.summary.contracts_expiring == 1
    expiring = [item for item in out.items if item.contract_expiring]
    assert [item.name for item in expiring] == ["Истекает"]


@pytest.mark.asyncio
async def test_portfolio_tenant_isolation(sessionmaker):
    async with sessionmaker() as session:
        await _seed(session, tenant_id="tenant-a", name="Чужой")
        await session.commit()
        out = await routes.portfolio(
            request=SimpleNamespace(headers={}),
            response=Response(),
            tenant=_tenant("tenant-b"),
            session=session,
            access=SimpleNamespace(),
            limit=50,
            offset=0,
        )
    assert out.total == 0


@pytest.mark.asyncio
async def test_portfolio_etag_304(sessionmaker):
    async with sessionmaker() as session:
        await _seed(session)
        await session.commit()
        resp1 = Response()
        await routes.portfolio(
            request=SimpleNamespace(headers={}),
            response=resp1,
            tenant=_tenant(),
            session=session,
            access=SimpleNamespace(),
            limit=50,
            offset=0,
        )
        etag = resp1.headers["etag"]
        again = await routes.portfolio(
            request=SimpleNamespace(headers={"if-none-match": etag}),
            response=Response(),
            tenant=_tenant(),
            session=session,
            access=SimpleNamespace(),
            limit=50,
            offset=0,
        )
    assert isinstance(again, Response) and again.status_code == 304


@pytest.mark.asyncio
async def test_feature_flag_off_returns_404(sessionmaker, monkeypatch):
    monkeypatch.setattr(routes, "is_feature_enabled", AsyncMock(return_value=False))
    async with sessionmaker() as session:
        with pytest.raises(HTTPException) as exc:
            await routes.portfolio(
                request=SimpleNamespace(headers={}),
                response=Response(),
                tenant=_tenant(),
                session=session,
                access=SimpleNamespace(),
                limit=50,
                offset=0,
            )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_soft_deleted_client_leaves_portfolio(sessionmaker):
    async with sessionmaker() as session:
        row = await _seed(session)
        await routes.delete_managed_client(
            mcid=row.id, tenant=_tenant(), session=session, access=SimpleNamespace()
        )
        out = await routes.portfolio(
            request=SimpleNamespace(headers={}),
            response=Response(),
            tenant=_tenant(),
            session=session,
            access=SimpleNamespace(),
            limit=50,
            offset=0,
        )
    assert out.total == 0
