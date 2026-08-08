"""BIZ-49 срез-14 — API переноса данных клиента (разд. 49.1)."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.api.routes import managed_clients as routes
from app.domains.managed_clients.lifecycle import ContractStatus, ManagedClientMode
from app.models.managed_clients import ManagedClient, ManagedClientTransfer
from app.models.master_data import Company, Person
from app.models.models import AuditLog, Tenant

_NOW = datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc)
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
    monkeypatch.setattr(routes, "is_feature_enabled", AsyncMock(return_value=True))


class _TrustedWrapper:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        self._orig_commit = self._session.commit
        self._session.commit = self._session.flush
        return self._session

    async def __aexit__(self, *exc):
        self._session.commit = self._orig_commit
        return False


async def _dedicated_client(session, *, with_target=True):
    company = Company(tenant_id=_TENANT, name="ООО Ромашка")
    session.add(company)
    await session.flush()
    row = ManagedClient(
        tenant_id=_TENANT,
        name="ООО Ромашка",
        mode=ManagedClientMode.DEDICATED,
        company_id=company.id,
        dedicated_tenant_slug="romashka",
        contract_status=ContractStatus.ACTIVE,
    )
    session.add(row)
    if with_target:
        session.add(
            Tenant(
                slug="romashka",
                code="romashka",
                name="Ромашка",
                schema_name="tenant_romashka",
                contact_email="r@r.ru",
            )
        )
    await session.flush()
    return row, company


async def _person(session, company_id, *, last_name="Иванов", **kw):
    row = Person(
        tenant_id=_TENANT,
        company_id=company_id,
        first_name="Иван",
        last_name=last_name,
        position_title="Слесарь",
        **kw,
    )
    session.add(row)
    await session.flush()
    return row


async def _transfer(session, mcid):
    with patch.object(routes, "_trusted_session", lambda: _TrustedWrapper(session)):
        return await routes.transfer_client_data(
            mcid=mcid,
            request=_request(),
            tenant=_tenant(),
            session=session,
            access=SimpleNamespace(),
            auth=_auth(),
        )


@pytest.mark.asyncio
async def test_transfer_copies_company_and_people(sessionmaker):
    async with sessionmaker() as session:
        client, company = await _dedicated_client(session)
        await _person(session, company.id, last_name="Иванов")
        await _person(session, company.id, last_name="Петров")

        out = await _transfer(session, client.id)
        assert out.status == "completed"
        # Ядро переноса; доменные счётчики срез-15 добавляет отдельными ключами.
        assert out.counts["company"] == 1
        assert out.counts["people"] == 2
        assert out.counts["people_skipped"] == 0

        target = (
            await session.execute(select(Tenant).where(Tenant.slug == "romashka"))
        ).scalar_one()
        copied_company = (
            await session.execute(select(Company).where(Company.tenant_id == target.id))
        ).scalar_one()
        assert copied_company.name == "ООО Ромашка"
        copied_people = (
            (await session.execute(select(Person).where(Person.tenant_id == target.id)))
            .scalars()
            .all()
        )
        assert sorted(p.last_name for p in copied_people) == ["Иванов", "Петров"]
        # каталожные ссылки обнулены, текстовая должность жива
        assert all(p.position_id is None and p.workplace_id is None for p in copied_people)
        assert all(p.position_title == "Слесарь" for p in copied_people)
        # исходные строки остались историей
        originals = (
            (await session.execute(select(Person).where(Person.tenant_id == _TENANT)))
            .scalars()
            .all()
        )
        assert len(originals) == 2


@pytest.mark.asyncio
async def test_transfer_skips_deleted_and_anonymized(sessionmaker):
    async with sessionmaker() as session:
        client, company = await _dedicated_client(session)
        await _person(session, company.id, last_name="Живой")
        await _person(session, company.id, last_name="Удалённый", deleted_at=_NOW)
        await _person(session, company.id, last_name="Обезличенный", anonymized_at=_NOW)

        out = await _transfer(session, client.id)
        assert out.counts["company"] == 1
        assert out.counts["people"] == 1
        assert out.counts["people_skipped"] == 2


@pytest.mark.asyncio
async def test_transfer_writes_journal_with_id_map_and_audit(sessionmaker):
    async with sessionmaker() as session:
        client, company = await _dedicated_client(session)
        person = await _person(session, company.id)

        await _transfer(session, client.id)

        journal = (
            await session.execute(
                select(ManagedClientTransfer).where(
                    ManagedClientTransfer.managed_client_id == client.id
                )
            )
        ).scalar_one()
        assert journal.status == "completed"
        assert company.id in journal.id_map["company"]
        assert person.id in journal.id_map["people"]

        audit = (
            (
                await session.execute(
                    select(AuditLog).where(AuditLog.action == "managed_client.data_transferred")
                )
            )
            .scalars()
            .all()
        )
        assert len(audit) == 1

        listed = await routes.list_client_transfers(
            mcid=client.id, tenant=_tenant(), session=session, access=SimpleNamespace()
        )
        assert [row.id for row in listed] == [journal.id]


@pytest.mark.asyncio
async def test_second_transfer_is_409(sessionmaker):
    async with sessionmaker() as session:
        client, company = await _dedicated_client(session)
        await _person(session, company.id)
        await _transfer(session, client.id)
        with pytest.raises(HTTPException) as exc:
            await _transfer(session, client.id)
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "MANAGED_CLIENT_TRANSFER_INVALID"


@pytest.mark.asyncio
async def test_lightweight_client_is_409(sessionmaker):
    async with sessionmaker() as session:
        company = Company(tenant_id=_TENANT, name="ООО Лайт")
        session.add(company)
        await session.flush()
        row = ManagedClient(
            tenant_id=_TENANT,
            name="ООО Лайт",
            mode=ManagedClientMode.LIGHTWEIGHT,
            company_id=company.id,
            contract_status=ContractStatus.ACTIVE,
        )
        session.add(row)
        await session.flush()
        with pytest.raises(HTTPException) as exc:
            await _transfer(session, row.id)
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "MANAGED_CLIENT_TRANSFER_INVALID"


@pytest.mark.asyncio
async def test_missing_target_tenant_is_409(sessionmaker):
    """Слаг записан, а арендатора нет — перевод не завершён или арендатор удалён."""
    async with sessionmaker() as session:
        client, _company = await _dedicated_client(session, with_target=False)
        with pytest.raises(HTTPException) as exc:
            await _transfer(session, client.id)
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "MANAGED_CLIENT_TRANSFER_TARGET_MISSING"


@pytest.mark.asyncio
async def test_missing_client_is_404(sessionmaker):
    async with sessionmaker() as session:
        with pytest.raises(HTTPException) as exc:
            await _transfer(session, "missing")
    assert exc.value.status_code == 404
