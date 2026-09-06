"""Контур БДД срез-5 (Доп. №1 разд. 56.2): инструктажи водителей.

Требование: «Инструктажи и стажировки водителей, проверки знаний ПДД/БДД,
приказы об ответственных». Этот срез закрывает ИНСТРУКТАЖИ. Стажировки и
проверки знаний — следующий срез: у них общая природа (допуск к
самостоятельной работе) и общий ядровой механизм аттестаций.

СВЕРКА нашла:

1. **Своего реестра заводить НЕ НАДО — и это подтвердилось.** Механизм
   инструктажей в ядре полный: журналы, записи, подписи, сроки. Не хватало
   ОДНОГО — видов БДД в закрытом словаре ``BRIEFING_TYPE_DISCIPLINE``. Ровно
   тот случай, про который говорит урок пяти срезов: контур готов, не хватает
   разметки. Комплект документов при этом уже печатал «Программу инструктажа
   водителей» — бумага есть, записать проведённое нечем.
2. **ТРИ КОПИИ ОДНОГО СЛОВАРЯ, И ДВЕ ИЗ НИХ ВРАЛИ.** Это находка не про БДД, а
   про весь продукт:

   * ``frontend/.../EmployeeCardPage.tsx`` — ключ ``repeated``, которого в
     ядре НИКОГДА не было (канон — ``repeat``): повторный инструктаж всё это
     время показывался на карточке сотрудника СЫРЫМ КОДОМ. Шести
     противопожарных видов, заведённых разд. 54.1, там не было вовсе;
   * ``backend/app/api/routes/pwa_sync.py`` — офлайн-справочник для телефона:
     ``"target"`` вместо ``"targeted"`` и опять ни одного противопожарного
     вида.

   Подстраховки нет ни там, ни там: ``labelFor`` печатает сырой ключ, а
   офлайн-справочник просто не содержит половины значений. Обе копии
   починены, офлайн-список теперь БЕРЁТСЯ ИЗ ЯДРА, а не пишется руками.

Решения:

* **свой реестр инструктажей НЕ заводится** — только разметка ядрового
  механизма (прецедент: пожарные виды в 54.1, дисциплина курса в 56.1);
* **четыре вида, а не один**: у сезонного и предрейсового разная
  периодичность, и свалить их в одно значило бы сделать контроль сроков
  невыполнимым — ровно то, из-за чего вид инструктажа перестал быть свободной
  строкой;
* **офлайн-справочник выводится из ядра**, а не дублируется: третья копия
  разошлась бы снова;
* **сводка БДД считает инструктажи, но реестром не владеет**: записи
  заводятся ядровыми ручками.

ГРАНИЦА: платформа НЕ решает, кого и как часто инструктировать — это следует
из вида перевозок и локальных приказов. Просрочка считается по ВНЕСЁННОМУ
сроку, а не по норме. Полей «требуется ли инструктаж» и «соблюдена ли
периодичность» нет ни в записи, ни в сводке.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import select

from app.core.disciplines import (
    BRIEFING_TYPE_DISCIPLINE,
    BRIEFING_TYPE_TITLES,
    BRIEFING_TYPES,
    Discipline,
)
from app.models.briefings import BriefingEntry, BriefingJournal
from app.models.feature import Feature, FeatureEnablement
from app.models.master_data import Company, EmploymentStatus, Person
from app.models.models import Tenant

pytestmark = pytest.mark.anyio

_API = "/api/v1/road-safety"
_REPO_ROOT = Path(__file__).resolve().parents[1]

ROAD_TYPES = {
    code
    for code, discipline in BRIEFING_TYPE_DISCIPLINE.items()
    if discipline is Discipline.ROAD_SAFETY
}


async def _grant(sessionmaker, code: str = "road_safety", on: bool = True) -> None:
    async with sessionmaker() as session:
        tenant = (
            await session.execute(select(Tenant).where(Tenant.slug == "test"))
        ).scalar_one()
        feature = (
            await session.execute(select(Feature).where(Feature.code == code))
        ).scalar_one_or_none()
        if feature is None:
            feature = Feature(code=code, title=code)
            session.add(feature)
            await session.flush()
        grant = (
            await session.execute(
                select(FeatureEnablement).where(
                    FeatureEnablement.tenant_id == tenant.id,
                    FeatureEnablement.feature_id == feature.id,
                )
            )
        ).scalar_one_or_none()
        if grant is None:
            session.add(
                FeatureEnablement(tenant_id=tenant.id, feature_id=feature.id, on=on)
            )
        else:
            grant.on = on
        await session.commit()


async def _briefing(
    sessionmaker,
    *,
    briefing_type: str,
    valid_until: datetime | None,
    terminated: bool = False,
) -> str:
    """Запись заводится ЯДРОВЫМ механизмом: своего реестра у БДД нет."""

    async with sessionmaker() as session:
        tenant = (
            await session.execute(select(Tenant).where(Tenant.slug == "test"))
        ).scalar_one()
        company = (
            (
                await session.execute(
                    select(Company).where(Company.tenant_id == tenant.id)
                )
            )
            .scalars()
            .first()
        )
        if company is None:
            company = Company(tenant_id=tenant.id, name="Головная компания")
            session.add(company)
            await session.flush()
        person = Person(
            tenant_id=tenant.id,
            company_id=company.id,
            last_name=f"Водителев{briefing_type}",
            first_name="Пётр",
            position_title="Водитель",
            employment_status=(
                EmploymentStatus.TERMINATED if terminated else EmploymentStatus.ACTIVE
            ),
        )
        journal = BriefingJournal(
            tenant_id=tenant.id,
            code=f"ЖУР-{briefing_type}",
            title="Журнал инструктажей",
            journal_type=briefing_type,
        )
        session.add_all([person, journal])
        await session.flush()
        entry = BriefingEntry(
            tenant_id=tenant.id,
            briefing_journal_id=journal.id,
            person_id=person.id,
            briefing_type=briefing_type,
            briefing_date=datetime.now(timezone.utc) - timedelta(days=200),
            valid_until=valid_until,
            status="signed",
        )
        session.add(entry)
        await session.commit()
        return str(entry.id)


class TestРазметкаВидов:
    def test_виды_бдд_заведены_и_размечены_дисциплиной(self) -> None:
        assert ROAD_TYPES == {
            "road_introductory",
            "road_pre_trip",
            "road_seasonal",
            "road_special",
        }

    def test_у_каждого_вида_есть_подпись_словами(self) -> None:
        """Без подписи вид уедет на экран и в журнал сырым кодом."""

        assert set(BRIEFING_TYPE_TITLES) == set(BRIEFING_TYPE_DISCIPLINE)
        for code in ROAD_TYPES:
            assert BRIEFING_TYPE_TITLES[code].strip()

    def test_видов_несколько_а_не_один(self) -> None:
        """У сезонного и предрейсового разная периодичность.

        Один общий вид «инструктаж по БДД» сделал бы контроль сроков
        невыполнимым — ровно то, из-за чего вид перестал быть свободной
        строкой в разд. 54.1.
        """

        assert len(ROAD_TYPES) >= 4

    def test_чужие_виды_не_переразмечены(self) -> None:
        """Сторож: срез добавляет своё, а не переписывает чужое."""

        assert BRIEFING_TYPE_DISCIPLINE["fire_ptm"] is Discipline.FIRE_SAFETY
        assert BRIEFING_TYPE_DISCIPLINE["repeat"] is Discipline.TRAINING


class TestКопииСловаря:
    """Найденный дрейф: три копии одного словаря, две врали."""

    def test_карточка_сотрудника_знает_те_же_виды(self) -> None:
        """Ключ ``repeated`` не существовал в ядре НИКОГДА.

        Из-за него повторный инструктаж показывался сырым кодом, а шести
        противопожарных видов из разд. 54.1 на карточке не было вовсе.
        Подстраховки нет: ``labelFor`` печатает ключ как есть.
        """

        page = (
            _REPO_ROOT / "frontend" / "src" / "pages" / "employees"
            / "EmployeeCardPage.tsx"
        )
        block = re.search(
            r"BRIEFING_TYPE_LABELS:\s*Record<string,\s*string>\s*=\s*\{(.*?)\n\};",
            page.read_text(encoding="utf-8"),
            re.S,
        )
        assert block is not None, "не нашёлся словарь видов инструктажа на фронте"
        front = set(re.findall(r"^\s*([a-z_]+):", block.group(1), re.M))
        assert front == set(BRIEFING_TYPES), sorted(front ^ set(BRIEFING_TYPES))

    def test_офлайн_справочник_выводится_из_ядра(self) -> None:
        """Телефон в поле получал справочник без половины значений.

        Список писался руками и разошёлся: ``"target"`` вместо ``"targeted"``
        и ни одного противопожарного вида. Теперь он выводится из ядра —
        третья копия иначе разойдётся снова.
        """

        from app.api.routes.pwa_sync import _build_dictionaries

        assert _build_dictionaries()["briefing_types"] == list(BRIEFING_TYPES)


class TestСводка:
    async def test_инструктажи_бдд_считаются_в_сводке(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        now = datetime.now(timezone.utc)
        await _briefing(
            sessionmaker,
            briefing_type="road_introductory",
            valid_until=now + timedelta(days=100),
        )
        await _briefing(
            sessionmaker,
            briefing_type="road_seasonal",
            valid_until=now - timedelta(days=10),
        )
        body = (await async_client.get(f"{_API}/readiness", headers=headers)).json()
        assert body["road_briefings_total"] == 2
        assert body["road_briefings_overdue"] == 1

    async def test_просрочка_уволенного_в_сводку_бдд_не_идёт(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """«Уволенный не в счёт» (BIZ-54-57 срез-95): запись в журнале и в общем
        счёте остаётся, а просрочкой не считается — как в календаре."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        now = datetime.now(timezone.utc)
        await _briefing(
            sessionmaker,
            briefing_type="road_seasonal",
            valid_until=now - timedelta(days=10),
        )
        await _briefing(
            sessionmaker,
            briefing_type="road_pre_trip",
            valid_until=now - timedelta(days=10),
            terminated=True,
        )
        body = (await async_client.get(f"{_API}/readiness", headers=headers)).json()
        assert body["road_briefings_total"] == 2, "журнал — история, цела"
        assert body["road_briefings_overdue"] == 1

    async def test_чужие_инструктажи_в_сводку_бдд_не_попадают(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Сторож: без отбора по видам сюда попал бы весь журнал предприятия."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        now = datetime.now(timezone.utc)
        await _briefing(
            sessionmaker, briefing_type="repeat", valid_until=now - timedelta(days=5)
        )
        await _briefing(
            sessionmaker, briefing_type="fire_ptm", valid_until=now - timedelta(days=5)
        )
        body = (await async_client.get(f"{_API}/readiness", headers=headers)).json()
        assert body["road_briefings_total"] == 0
        assert body["road_briefings_overdue"] == 0

    async def test_без_внесённого_срока_просрочки_нет(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """«Срок не внесён» и «просрочено» — разные вещи (канон срезов 1–3)."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        await _briefing(
            sessionmaker, briefing_type="road_pre_trip", valid_until=None
        )
        body = (await async_client.get(f"{_API}/readiness", headers=headers)).json()
        assert body["road_briefings_total"] == 1
        assert body["road_briefings_overdue"] == 0

    async def test_вердикта_о_периодичности_в_сводке_нет(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """ГРАНИЦА: кого и как часто инструктировать — не решение платформы."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        body = (await async_client.get(f"{_API}/readiness", headers=headers)).json()
        assert not any(
            key in body
            for key in (
                "road_briefings_required",
                "briefing_schedule_compliant",
                "briefings_missing",
            )
        )
