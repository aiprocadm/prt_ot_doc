"""BIZ-49 срез-13 — API перевода Lightweight → Dedicated (разд. 49.1)."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.api.routes import managed_clients as routes
from app.domains.managed_clients.lifecycle import ContractStatus, ManagedClientMode
from app.models.managed_clients import ManagedClient
from app.models.models import AuditLog, Tenant, User
from app.schemas.managed_clients import ConvertToDedicated

_NOW = datetime(2026, 8, 7, 12, 0, tzinfo=timezone.utc)
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


async def _client(session, *, mode=ManagedClientMode.LIGHTWEIGHT, status=ContractStatus.ACTIVE):
    row = ManagedClient(
        tenant_id=_TENANT,
        name="ООО Ромашка",
        mode=mode,
        company_id="comp-a" if mode is ManagedClientMode.LIGHTWEIGHT else None,
        dedicated_tenant_slug=None if mode is ManagedClientMode.LIGHTWEIGHT else "already",
        contract_status=status,
    )
    session.add(row)
    await session.flush()
    return row


class _TrustedWrapper:
    """Тестовая «доверенная сессия»: та же сессия теста, commit → flush.

    Реальная межарендаторная механика (_trusted_session с rls_bypass под
    FORCE RLS) проверяется отдельным db-тестом на живом PostgreSQL.
    """

    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        self._orig_commit = self._session.commit
        self._session.commit = self._session.flush
        return self._session

    async def __aexit__(self, *exc):
        self._session.commit = self._orig_commit
        return False


async def _convert(session, mcid, *, slug="romashka", email="owner@romashka.ru"):
    with patch.object(routes, "_trusted_session", lambda: _TrustedWrapper(session)):
        return await routes.convert_to_dedicated(
            mcid=mcid,
            payload=ConvertToDedicated(
                tenant_slug=slug, owner_email=email, owner_password="Secret123!"
            ),
            request=_request(),
            tenant=_tenant(),
            session=session,
            access=SimpleNamespace(),
            auth=_auth(),
        )


@pytest.mark.asyncio
async def test_conversion_creates_tenant_and_keeps_history(sessionmaker):
    """Ядро истории (строка клиента + организация) не теряется."""
    async with sessionmaker() as session:
        c = await _client(session)
        out = await _convert(session, c.id)

        assert out.client.mode == ManagedClientMode.DEDICATED
        assert out.tenant_slug == "romashka"
        # организация осталась ссылкой на историю
        assert out.history_company_id == "comp-a"
        assert out.client.company_id == "comp-a"

        # арендатор реально создан, с владельцем
        t = (await session.execute(select(Tenant).where(Tenant.slug == "romashka"))).scalar_one()
        owner = (
            (await session.execute(select(User).where(User.tenant_id == t.id))).scalars().first()
        )
        assert owner is not None and owner.email == "owner@romashka.ru"


@pytest.mark.asyncio
async def test_conversion_is_audited(sessionmaker):
    async with sessionmaker() as session:
        c = await _client(session)
        await _convert(session, c.id)
        rows = (
            (
                await session.execute(
                    select(AuditLog).where(
                        AuditLog.action == "managed_client.converted_to_dedicated"
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1


@pytest.mark.asyncio
async def test_dedicated_cannot_convert_twice(sessionmaker):
    async with sessionmaker() as session:
        c = await _client(session, mode=ManagedClientMode.DEDICATED)
        with pytest.raises(HTTPException) as exc:
            await _convert(session, c.id)
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "MANAGED_CLIENT_CONVERSION_INVALID"


@pytest.mark.asyncio
async def test_terminated_contract_blocks_conversion(sessionmaker):
    async with sessionmaker() as session:
        c = await _client(session, status=ContractStatus.TERMINATED)
        with pytest.raises(HTTPException) as exc:
            await _convert(session, c.id)
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "MANAGED_CLIENT_CONVERSION_INVALID"


@pytest.mark.asyncio
async def test_taken_slug_is_409(sessionmaker):
    """Перевод в ЧУЖОЙ арендатор пришил бы клиента к чужим данным."""
    async with sessionmaker() as session:
        session.add(
            Tenant(
                slug="busy",
                code="busy",
                name="Занятый",
                schema_name="tenant_busy",
                contact_email="busy@example.com",
            )
        )
        await session.flush()
        c = await _client(session)
        with pytest.raises(HTTPException) as exc:
            await _convert(session, c.id, slug="busy")
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "MANAGED_CLIENT_TENANT_SLUG_TAKEN"


@pytest.mark.asyncio
async def test_slug_is_normalized_to_lowercase(sessionmaker):
    async with sessionmaker() as session:
        c = await _client(session)
        out = await _convert(session, c.id, slug="Romashka")
    assert out.tenant_slug == "romashka"


@pytest.mark.asyncio
async def test_missing_client_is_404(sessionmaker):
    async with sessionmaker() as session:
        with pytest.raises(HTTPException) as exc:
            await _convert(session, "missing")
    assert exc.value.status_code == 404
