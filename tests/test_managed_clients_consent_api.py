"""BIZ-49 срез-12 — API согласия клиента на делегированный доступ (разд. 66.3)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
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
    ManagedClientContextSession,
)
from app.models.models import AuditLog
from app.schemas.managed_clients import AccessGrantCreate, ConsentCreate, ConsentRevoke

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
        url=SimpleNamespace(path="/api/v1/managed-clients/x/consents"),
        method="POST",
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
    return row


async def _record(session, client_id, *, document_ref="Поручение №1", expires_at=None):
    return await routes.record_client_consent(
        mcid=client_id,
        payload=ConsentCreate(document_ref=document_ref, expires_at=expires_at),
        request=_request(),
        tenant=_tenant(),
        session=session,
        access=SimpleNamespace(),
        auth=_auth(),
    )


# --- фиксация ---------------------------------------------------------------
@pytest.mark.asyncio
async def test_record_consent_and_read_back(sessionmaker):
    async with sessionmaker() as session:
        c = await _client(session)
        out = await _record(session, c.id)
        assert out.active is True
        assert out.document_ref == "Поручение №1"
        assert out.granted_by_user_id == "admin-1"

        listed = await routes.list_client_consents(
            mcid=c.id, tenant=_tenant(), session=session, access=SimpleNamespace()
        )
        assert [row.id for row in listed] == [out.id]


@pytest.mark.asyncio
async def test_blank_document_ref_is_422(sessionmaker):
    """Согласие «на словах» не основание."""
    async with sessionmaker() as session:
        c = await _client(session)
        with pytest.raises(HTTPException) as exc:
            await _record(session, c.id, document_ref="   ")
    assert exc.value.status_code == 422
    assert exc.value.detail["code"] == "MANAGED_CLIENT_CONSENT_INVALID"


@pytest.mark.asyncio
async def test_same_active_document_twice_is_409(sessionmaker):
    """Даблклик не должен плодить два «основания» по одному документу."""
    async with sessionmaker() as session:
        c = await _client(session)
        await _record(session, c.id)
        with pytest.raises(HTTPException) as exc:
            await _record(session, c.id)
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "MANAGED_CLIENT_CONSENT_EXISTS"


@pytest.mark.asyncio
async def test_record_writes_audit(sessionmaker):
    """Фиксация согласия — событие безопасности."""
    async with sessionmaker() as session:
        c = await _client(session)
        await _record(session, c.id)
        rows = (
            (
                await session.execute(
                    select(AuditLog).where(AuditLog.action == "managed_client.consent.grant")
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1


# --- грант требует согласия -------------------------------------------------
@pytest.mark.asyncio
async def test_grant_without_consent_is_409(sessionmaker):
    async with sessionmaker() as session:
        c = await _client(session)
        with pytest.raises(HTTPException) as exc:
            await routes.grant_access(
                mcid=c.id,
                payload=AccessGrantCreate(user_id="u1", all_modules=True),
                request=_request(),
                tenant=_tenant(),
                session=session,
                access=SimpleNamespace(),
                auth=_auth(),
            )
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "MANAGED_CLIENT_CONSENT_REQUIRED"


@pytest.mark.asyncio
async def test_grant_with_consent_succeeds(sessionmaker):
    async with sessionmaker() as session:
        c = await _client(session)
        await _record(session, c.id)
        out = await routes.grant_access(
            mcid=c.id,
            payload=AccessGrantCreate(user_id="u1", all_modules=True),
            request=_request(),
            tenant=_tenant(),
            session=session,
            access=SimpleNamespace(),
            auth=_auth(),
        )
    assert out.active is True


@pytest.mark.asyncio
async def test_grant_with_expired_consent_is_409(sessionmaker):
    """Истёкшее согласие равно отозванному."""
    async with sessionmaker() as session:
        c = await _client(session)
        session.add(
            ManagedClientConsent(
                tenant_id=_TENANT,
                managed_client_id=c.id,
                document_ref="Поручение №0",
                granted_at=_NOW - timedelta(days=400),
                expires_at=_NOW - timedelta(days=35),
            )
        )
        await session.flush()
        with pytest.raises(HTTPException) as exc:
            await routes.grant_access(
                mcid=c.id,
                payload=AccessGrantCreate(user_id="u1", all_modules=True),
                request=_request(),
                tenant=_tenant(),
                session=session,
                access=SimpleNamespace(),
                auth=_auth(),
            )
    assert exc.value.detail["code"] == "MANAGED_CLIENT_CONSENT_REQUIRED"


# --- вход в контекст требует согласия ---------------------------------------
@pytest.mark.asyncio
async def test_context_denied_without_consent_even_with_grant(sessionmaker):
    """Гранты долгоживущие: согласие могло быть отозвано ПОСЛЕ выдачи гранта."""
    async with sessionmaker() as session:
        c = await _client(session)
        session.add(
            ManagedClientAccess(
                tenant_id=_TENANT,
                managed_client_id=c.id,
                user_id="admin-1",
                all_modules=True,
                modules=[],
                granted_at=_NOW,
            )
        )
        await session.flush()
        with pytest.raises(HTTPException) as exc:
            await routes.enter_client_context(
                mcid=c.id,
                request=_request(),
                tenant=_tenant(),
                session=session,
                access=SimpleNamespace(),
                auth=_auth(),
            )
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "MANAGED_CLIENT_CONSENT_REQUIRED"


# --- отзыв ------------------------------------------------------------------
@pytest.mark.asyncio
async def test_revoke_is_trace_not_delete_and_closes_sessions(sessionmaker):
    """Отзыв — след; открытые сессии «от имени» закрываются немедленно."""
    async with sessionmaker() as session:
        c = await _client(session)
        consent = await _record(session, c.id)
        session.add(
            ManagedClientContextSession(
                tenant_id=_TENANT,
                managed_client_id=c.id,
                user_id="u1",
                started_at=_NOW,
            )
        )
        await session.flush()

        out = await routes.revoke_client_consent(
            mcid=c.id,
            consent_id=consent.id,
            payload=ConsentRevoke(reason="клиент расторг договор"),
            request=_request(),
            tenant=_tenant(),
            session=session,
            access=SimpleNamespace(),
            auth=_auth(),
        )
        assert out.active is False
        assert out.revoked_by_user_id == "admin-1"
        assert out.revoke_reason == "клиент расторг договор"

        # строка осталась (след), а не удалена
        still = (
            await session.execute(
                select(ManagedClientConsent).where(ManagedClientConsent.id == consent.id)
            )
        ).scalar_one()
        assert still.revoked_at is not None

        closed = (
            await session.execute(
                select(ManagedClientContextSession).where(
                    ManagedClientContextSession.managed_client_id == c.id
                )
            )
        ).scalar_one()
        assert closed.ended_at is not None
        assert closed.ended_reason == "consent_revoked"

        audit = (
            (
                await session.execute(
                    select(AuditLog).where(AuditLog.action == "managed_client.consent.revoke")
                )
            )
            .scalars()
            .all()
        )
        assert len(audit) == 1


@pytest.mark.asyncio
async def test_revoke_twice_is_409(sessionmaker):
    async with sessionmaker() as session:
        c = await _client(session)
        consent = await _record(session, c.id)
        await routes.revoke_client_consent(
            mcid=c.id,
            consent_id=consent.id,
            payload=None,
            request=_request(),
            tenant=_tenant(),
            session=session,
            access=SimpleNamespace(),
            auth=_auth(),
        )
        with pytest.raises(HTTPException) as exc:
            await routes.revoke_client_consent(
                mcid=c.id,
                consent_id=consent.id,
                payload=None,
                request=_request(),
                tenant=_tenant(),
                session=session,
                access=SimpleNamespace(),
                auth=_auth(),
            )
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "MANAGED_CLIENT_CONSENT_ALREADY_REVOKED"


@pytest.mark.asyncio
async def test_revoked_consents_stay_in_listing(sessionmaker):
    """Прошлые согласия — вопрос аудита, а не истории."""
    async with sessionmaker() as session:
        c = await _client(session)
        consent = await _record(session, c.id)
        await routes.revoke_client_consent(
            mcid=c.id,
            consent_id=consent.id,
            payload=None,
            request=_request(),
            tenant=_tenant(),
            session=session,
            access=SimpleNamespace(),
            auth=_auth(),
        )
        listed = await routes.list_client_consents(
            mcid=c.id, tenant=_tenant(), session=session, access=SimpleNamespace()
        )
    assert len(listed) == 1
    assert listed[0].active is False


@pytest.mark.asyncio
async def test_revoke_missing_consent_is_404(sessionmaker):
    async with sessionmaker() as session:
        c = await _client(session)
        with pytest.raises(HTTPException) as exc:
            await routes.revoke_client_consent(
                mcid=c.id,
                consent_id="missing",
                payload=None,
                request=_request(),
                tenant=_tenant(),
                session=session,
                access=SimpleNamespace(),
                auth=_auth(),
            )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_consent_of_another_tenant_is_invisible(sessionmaker):
    """Согласие чужого арендатора не найдено — изоляция как у грантов."""
    async with sessionmaker() as session:
        c = await _client(session)
        foreign = await _client(session, name="Чужой", tenant_id="tenant-2")
        session.add(
            ManagedClientConsent(
                tenant_id="tenant-2",
                managed_client_id=foreign.id,
                document_ref="Чужое поручение",
                granted_at=_NOW,
            )
        )
        await session.flush()
        listed = await routes.list_client_consents(
            mcid=c.id, tenant=_tenant(), session=session, access=SimpleNamespace()
        )
    assert listed == []
