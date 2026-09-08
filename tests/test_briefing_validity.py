"""Срок инструктажа — по человеку × виду (BIZ-54-57 срез-85, разд. 54.1 / 57.1).

Одно правило на три экрана: строка ПБ светофора (срез-83/84), готовность к
проверке МЧС и вкладка инструктажей карточки сотрудника (срез-85) считают
«истёк / действует» через ``services/briefing_validity``. Здесь закрепляется
само правило, без экранов:

- у каждой пары (человек, вид) — самая поздняя дата действия, старые записи
  того же вида не считаются;
- виды друг друга не закрывают: ПТМ повторным не закрыть;
- запись без человека — сама себе владелец (по ``id``), а не общая куча;
- запись без срока и удалённая запись правила не касаются;
- пустой список людей — пустой ответ, а не «все люди арендатора».
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.models.briefings import BriefingEntry, BriefingJournal
from app.models.master_data import EmploymentStatus
from app.modules.briefings.services import BriefingEntryService
from app.services.briefing_validity import latest_briefing_validity

pytestmark = pytest.mark.anyio

NOW = datetime.now(tz=timezone.utc)


def _entry(tenant, journal, *, person_id=None, briefing_type: str, valid_days: int | None):
    return BriefingEntry(
        tenant_id=tenant.id,
        briefing_journal_id=journal.id,
        person_id=person_id,
        briefing_type=briefing_type,
        briefing_date=NOW - timedelta(days=1),
        valid_until=None if valid_days is None else NOW + timedelta(days=valid_days),
        status="completed",
    )


@pytest.fixture()
async def journal_with_people(sessionmaker, data_factory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, name="АКМЕ", session=session)
        ivanov = await data_factory.create_person(
            tenant=tenant, company=company, last_name="Иванов", session=session
        )
        petrov = await data_factory.create_person(
            tenant=tenant, company=company, last_name="Петров", session=session
        )
        journal = BriefingJournal(
            tenant_id=tenant.id, code="J-V", title="Журнал", journal_type="all"
        )
        session.add(journal)
        await session.flush()
        entries = [
            # Иванов: повторный ПБ — старая и свежая; ПТМ — только истёкший
            _entry(
                tenant, journal, person_id=ivanov.id, briefing_type="fire_repeat", valid_days=-200
            ),
            _entry(
                tenant, journal, person_id=ivanov.id, briefing_type="fire_repeat", valid_days=150
            ),
            _entry(tenant, journal, person_id=ivanov.id, briefing_type="fire_ptm", valid_days=-30),
            # Иванов: запись без срока — правила не касается
            _entry(tenant, journal, person_id=ivanov.id, briefing_type="targeted", valid_days=None),
            # Петров: одна действующая по ОТ
            _entry(tenant, journal, person_id=petrov.id, briefing_type="primary", valid_days=300),
            # без человека: сама себе владелец
            _entry(tenant, journal, briefing_type="fire_introductory", valid_days=-10),
        ]
        deleted = _entry(
            tenant, journal, person_id=petrov.id, briefing_type="repeat", valid_days=-5
        )
        deleted.deleted_at = NOW
        session.add_all([*entries, deleted])
        await session.commit()
        return tenant, str(ivanov.id), str(petrov.id), str(entries[-1].id)


async def test_самая_поздняя_дата_на_пару_человек_вид(sessionmaker, journal_with_people) -> None:
    tenant, ivanov, _petrov, _orphan = journal_with_people
    async with sessionmaker() as session:
        latest = await latest_briefing_validity(
            session, tenant_id=str(tenant.id), person_ids=[ivanov]
        )

    assert set(latest) == {(ivanov, "fire_repeat"), (ivanov, "fire_ptm")}
    assert latest[(ivanov, "fire_repeat")] > NOW, "старая запись повторного перекрыта свежей"
    assert latest[(ivanov, "fire_ptm")] < NOW, "а ПТМ повторным не закрыть"
    assert all(moment.tzinfo is not None for moment in latest.values())


async def test_фильтр_по_видам_и_по_людям(sessionmaker, journal_with_people) -> None:
    tenant, ivanov, petrov, _orphan = journal_with_people
    async with sessionmaker() as session:
        only_ptm = await latest_briefing_validity(
            session,
            tenant_id=str(tenant.id),
            person_ids=[ivanov, petrov],
            briefing_types=["fire_ptm"],
        )
        both = await latest_briefing_validity(
            session, tenant_id=str(tenant.id), person_ids=[ivanov, petrov]
        )

    assert set(only_ptm) == {(ivanov, "fire_ptm")}
    assert set(both) == {(ivanov, "fire_repeat"), (ivanov, "fire_ptm"), (petrov, "primary")}


async def test_без_списка_людей_весь_арендатор_и_сирота_сама_себе_владелец(
    sessionmaker, journal_with_people
) -> None:
    tenant, ivanov, petrov, orphan = journal_with_people
    async with sessionmaker() as session:
        latest = await latest_briefing_validity(session, tenant_id=str(tenant.id), person_ids=None)

    assert (orphan, "fire_introductory") in latest
    assert {owner for owner, _ in latest} == {ivanov, petrov, orphan}
    # удалённая запись Петрова по повторному не воскресает
    assert (petrov, "repeat") not in latest


async def test_пустой_список_людей_это_пусто_а_не_все(sessionmaker, journal_with_people) -> None:
    tenant, *_ = journal_with_people
    async with sessionmaker() as session:
        assert (
            await latest_briefing_validity(session, tenant_id=str(tenant.id), person_ids=[]) == {}
        )


async def test_без_списка_людей_уволенный_и_удалённый_не_в_счёт(sessionmaker, data_factory) -> None:
    """Срез-94: сводка модуля ПБ (``person_ids=None``) считает только работающих;
    запись без человека остаётся; явный список — ровно эти люди."""

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, name="АКМЕ", session=session)
        here = await data_factory.create_person(
            tenant=tenant, company=company, last_name="Работающий", session=session
        )
        gone = await data_factory.create_person(
            tenant=tenant,
            company=company,
            last_name="Уволенный",
            employment_status=EmploymentStatus.TERMINATED,
            session=session,
        )
        erased = await data_factory.create_person(
            tenant=tenant, company=company, last_name="Удалённый", deleted_at=NOW, session=session
        )
        journal = BriefingJournal(
            tenant_id=tenant.id, code="J-T", title="Журнал", journal_type="all"
        )
        session.add(journal)
        await session.flush()
        orphan = _entry(tenant, journal, briefing_type="fire_ptm", valid_days=-10)
        session.add_all(
            [
                _entry(
                    tenant, journal, person_id=here.id, briefing_type="fire_ptm", valid_days=-10
                ),
                _entry(
                    tenant, journal, person_id=gone.id, briefing_type="fire_ptm", valid_days=-10
                ),
                _entry(
                    tenant, journal, person_id=erased.id, briefing_type="fire_ptm", valid_days=-10
                ),
                orphan,
            ]
        )
        await session.commit()
        tenant_id, here_id, gone_id, orphan_id = (
            str(tenant.id),
            str(here.id),
            str(gone.id),
            str(orphan.id),
        )

    async with sessionmaker() as session:
        everyone = await latest_briefing_validity(session, tenant_id=tenant_id, person_ids=None)
        explicit = await latest_briefing_validity(
            session, tenant_id=tenant_id, person_ids=[gone_id]
        )

    assert {owner for owner, _ in everyone} == {here_id, orphan_id}
    assert {owner for owner, _ in explicit} == {gone_id}


class TestПросроченныеИнструктажи:
    """Список и рассылка «просрочено» считают одно множество людей (срез-115).

    Кнопка «напомнить о просроченных» (``POST /briefings/entries/remind-overdue``)
    берёт данные из того же ``list_overdue``, что и экран. До среза отбор не знал
    правила «уволенный не в счёт»: просроченный инструктаж уволенного попадал и
    в список, и в рассылку — напоминание уходило по тому, кого в организации
    больше нет.
    """

    async def test_уволенный_и_удалённый_не_попадают_а_запись_без_человека_остаётся(
        self, sessionmaker, data_factory
    ) -> None:
        async with sessionmaker() as session:
            tenant = await data_factory.ensure_tenant(session=session)
            company = await data_factory.create_company(
                tenant=tenant, name="АКМЕ-115", session=session
            )
            here = await data_factory.create_person(
                tenant=tenant, company=company, last_name="Работает", session=session
            )
            gone = await data_factory.create_person(
                tenant=tenant,
                company=company,
                last_name="Уволен",
                session=session,
                employment_status=EmploymentStatus.TERMINATED,
            )
            erased = await data_factory.create_person(
                tenant=tenant, company=company, last_name="Удалён", session=session
            )
            erased.deleted_at = NOW
            journal = BriefingJournal(
                tenant_id=tenant.id, code="J-115", title="Журнал", journal_type="all"
            )
            session.add(journal)
            await session.flush()
            entries = [
                _entry(tenant, journal, person_id=here.id, briefing_type="repeat", valid_days=-10),
                _entry(tenant, journal, person_id=gone.id, briefing_type="repeat", valid_days=-10),
                _entry(
                    tenant, journal, person_id=erased.id, briefing_type="repeat", valid_days=-10
                ),
                # Инструктаж без человека (по подразделению) — увольнять некого.
                _entry(tenant, journal, briefing_type="targeted", valid_days=-10),
            ]
            for entry in entries:
                entry.status = "planned"
            session.add_all(entries)
            await session.commit()

            overdue = await BriefingEntryService().list_overdue(session, tenant_id=str(tenant.id))

        person_ids = {item.person_id for item in overdue}
        assert here.id in person_ids
        assert gone.id not in person_ids
        assert erased.id not in person_ids
        assert None in person_ids, "запись без человека должна остаться видимой"
