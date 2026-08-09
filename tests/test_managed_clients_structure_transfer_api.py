"""BIZ-49 срез-16 — структура организации и оставшаяся история (разд. 49.1).

Главное здесь — исправление среза-14: должность и рабочее место висят на
организации клиента (``company_id`` NOT NULL), то есть это ЕГО данные, а не
каталог аутсорсера. Обнуляя их, платформа лишала перенесённого человека
структурных связей, по которым считаются нормы медосмотров и СИЗ.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.api.routes import managed_clients as routes
from app.domains.managed_clients.lifecycle import ContractStatus, ManagedClientMode
from app.models.field_ops import Permit
from app.models.incidents import (
    Incident,
    IncidentLog,
    IncidentPerson,
    IncidentPersonRole,
    IncidentStage,
    IncidentStatus,
)
from app.models.journals import Journal, JournalEntry, JournalType
from app.models.managed_clients import ManagedClient
from app.models.master_data import Company, Person, Position, Site, Workplace
from app.models.models import Tenant

_NOW = datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc)
_TODAY = date(2026, 8, 8)
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


async def _setup(session):
    """Клиент Dedicated: организация со структурой и сотрудником."""

    company = Company(tenant_id=_TENANT, name="ООО Ромашка")
    session.add(company)
    await session.flush()
    site = Site(tenant_id=_TENANT, company_id=company.id, name="Площадка Север", address="Мурманск")
    position = Position(tenant_id=_TENANT, company_id=company.id, name="Слесарь")
    session.add_all([site, position])
    await session.flush()
    workplace = Workplace(tenant_id=_TENANT, company_id=company.id, site_id=site.id, name="РМ-1")
    session.add(workplace)
    session.add(
        Tenant(
            slug="romashka",
            code="romashka",
            name="Ромашка",
            schema_name="tenant_romashka",
            contact_email="r@r.ru",
        )
    )
    client = ManagedClient(
        tenant_id=_TENANT,
        name="ООО Ромашка",
        mode=ManagedClientMode.DEDICATED,
        company_id=company.id,
        dedicated_tenant_slug="romashka",
        contract_status=ContractStatus.ACTIVE,
    )
    session.add(client)
    await session.flush()
    person = Person(
        tenant_id=_TENANT,
        company_id=company.id,
        position_id=position.id,
        workplace_id=workplace.id,
        first_name="Иван",
        last_name="Иванов",
        position_title="Слесарь",
    )
    session.add(person)
    await session.flush()
    return SimpleNamespace(
        client=client,
        company=company,
        site=site,
        position=position,
        workplace=workplace,
        person=person,
    )


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


async def _target_id(session) -> str:
    row = (await session.execute(select(Tenant).where(Tenant.slug == "romashka"))).scalar_one()
    return row.id


@pytest.mark.asyncio
async def test_structure_moves_and_person_links_are_remapped(sessionmaker):
    """Исправление среза-14: ссылки человека перевешиваются, а не обнуляются."""

    async with sessionmaker() as session:
        env = await _setup(session)
        out = await _transfer(session, env.client.id)
        assert out.counts["sites"] == 1
        assert out.counts["positions"] == 1
        assert out.counts["workplaces"] == 1

        target = await _target_id(session)
        new_site = (
            await session.execute(select(Site).where(Site.tenant_id == target))
        ).scalar_one()
        new_position = (
            await session.execute(select(Position).where(Position.tenant_id == target))
        ).scalar_one()
        new_workplace = (
            await session.execute(select(Workplace).where(Workplace.tenant_id == target))
        ).scalar_one()
        new_person = (
            await session.execute(select(Person).where(Person.tenant_id == target))
        ).scalar_one()

        assert new_site.name == "Площадка Север"
        # Рабочее место ссылается на КОПИЮ площадки, а не на площадку аутсорсера.
        assert new_workplace.site_id == new_site.id
        # Человек связан со СВОЕЙ структурой в новом арендаторе.
        assert new_person.position_id == new_position.id
        assert new_person.workplace_id == new_workplace.id


@pytest.mark.asyncio
async def test_permits_and_journals_move_with_remapped_links(sessionmaker):
    async with sessionmaker() as session:
        env = await _setup(session)
        session.add(
            Permit(
                tenant_id=_TENANT,
                person_id=env.person.id,
                position_id=env.position.id,
                permit_type="работы на высоте",
                issued_at=_TODAY,
            )
        )
        journal = Journal(
            tenant_id=_TENANT,
            company_id=env.company.id,
            title="Журнал вводного инструктажа",
            journal_type=JournalType.INTRODUCTORY,
        )
        session.add(journal)
        await session.flush()
        session.add(
            JournalEntry(
                tenant_id=_TENANT,
                journal_id=journal.id,
                person_id=env.person.id,
                entry_type=JournalType.INTRODUCTORY,
                entry_date=_TODAY,
                instructor="Петров",
            )
        )
        await session.flush()

        out = await _transfer(session, env.client.id)
        assert out.counts["permits"] == 1
        assert out.counts["journals"] == 1
        assert out.counts["journal_entries"] == 1

        target = await _target_id(session)
        new_permit = (
            await session.execute(select(Permit).where(Permit.tenant_id == target))
        ).scalar_one()
        new_position = (
            await session.execute(select(Position).where(Position.tenant_id == target))
        ).scalar_one()
        new_journal = (
            await session.execute(select(Journal).where(Journal.tenant_id == target))
        ).scalar_one()
        new_entry = (
            await session.execute(select(JournalEntry).where(JournalEntry.tenant_id == target))
        ).scalar_one()

        assert new_permit.permit_type == "работы на высоте"
        assert new_permit.position_id == new_position.id
        assert new_entry.journal_id == new_journal.id
        assert new_entry.instructor == "Петров"


@pytest.mark.asyncio
async def test_incidents_move_with_participants_and_logs(sessionmaker):
    async with sessionmaker() as session:
        env = await _setup(session)
        incident = Incident(
            tenant_id=_TENANT,
            company_id=env.company.id,
            site_id=env.site.id,
            title="Падение с высоты",
            occurred_at=_NOW,
            # Пакет документов — инструмент аутсорсера.
            pack_id=None,
        )
        session.add(incident)
        await session.flush()
        session.add(
            IncidentPerson(
                tenant_id=_TENANT,
                incident_id=incident.id,
                person_id=env.person.id,
                role=IncidentPersonRole.VICTIM,
            )
        )
        session.add(
            IncidentLog(
                tenant_id=_TENANT,
                incident_id=incident.id,
                author_id=None,
                stage=IncidentStage.REGISTRATION,
                status=IncidentStatus.REPORTED,
                message="Зарегистрировано",
            )
        )
        await session.flush()

        out = await _transfer(session, env.client.id)
        assert out.counts["incidents"] == 1
        assert out.counts["incident_participants"] == 1
        assert out.counts["incident_logs"] == 1

        target = await _target_id(session)
        new_incident = (
            await session.execute(select(Incident).where(Incident.tenant_id == target))
        ).scalar_one()
        new_site = (
            await session.execute(select(Site).where(Site.tenant_id == target))
        ).scalar_one()
        new_person = (
            await session.execute(select(Person).where(Person.tenant_id == target))
        ).scalar_one()
        participant = (
            await session.execute(select(IncidentPerson).where(IncidentPerson.tenant_id == target))
        ).scalar_one()
        log = (
            await session.execute(select(IncidentLog).where(IncidentLog.tenant_id == target))
        ).scalar_one()

        # Происшествие сшито с КОПИЯМИ площадки и человека.
        assert new_incident.site_id == new_site.id
        assert participant.person_id == new_person.id
        assert participant.incident_id == new_incident.id
        # Пакет документов аутсорсера не поехал, автор записи снят.
        assert new_incident.pack_id is None
        assert log.author_id is None


@pytest.mark.asyncio
async def test_history_of_other_company_stays(sessionmaker):
    """Журнал и происшествие другой организации аутсорсера не переносятся."""

    async with sessionmaker() as session:
        env = await _setup(session)
        other = Company(tenant_id=_TENANT, name="ООО Чужая")
        session.add(other)
        await session.flush()
        other_site = Site(tenant_id=_TENANT, company_id=other.id, name="Чужая площадка")
        other_journal = Journal(
            tenant_id=_TENANT,
            company_id=other.id,
            title="Чужой журнал",
            journal_type=JournalType.PRIMARY,
        )
        session.add_all([other_site, other_journal])
        await session.flush()
        session.add(
            Incident(
                tenant_id=_TENANT,
                company_id=other.id,
                site_id=other_site.id,
                title="Чужое происшествие",
                occurred_at=_NOW,
            )
        )
        # Запись журнала СВОЕГО человека, но в ЧУЖОМ журнале: journal_id
        # NOT NULL, подставить нечего — строка остаётся у аутсорсера.
        session.add(
            JournalEntry(
                tenant_id=_TENANT,
                journal_id=other_journal.id,
                person_id=env.person.id,
                entry_type=JournalType.PRIMARY,
                entry_date=_TODAY,
            )
        )
        await session.flush()

        out = await _transfer(session, env.client.id)
        assert out.counts["incidents"] == 0
        assert out.counts["journals"] == 0
        assert out.counts["journal_entries"] == 0
        assert out.counts["journal_entries_skipped"] == 1

        target = await _target_id(session)
        sites = (
            (await session.execute(select(Site).where(Site.tenant_id == target))).scalars().all()
        )
        assert [s.name for s in sites] == ["Площадка Север"]
