"""Светофор дисциплин на карточке сотрудника (BIZ-54-57 срез-53, Доп. №1 разд. 57.1).

ТЗ: «карточка сотрудника 360°: все его обучения, допуски, медосмотры, СИЗ,
аттестации по всем дисциплинам сразу». Вкладки карточки показывали записи, но
не отвечали «всё ли положенное у человека действует». Здесь закрепляется:

- строка на КАЖДУЮ дисциплину словаря, в порядке словаря, теми же словами;
- числа — ТЕ ЖЕ, что у карточки площадки, где этот человек единственный
  (одни правила, а не второй расчёт);
- «эталон не задан» говорит про должность человека, а не «должности клиента»;
- уволенный не красится: «не измеряется» с причиной, итог ``not_measured``;
- неизмеримые дисциплины в итог не входят: зелёные медосмотры и СИЗ дают
  зелёный итог, а не «неизвестно»;
- (срез-64) у допущенного водителя строка «БДД» считается по удостоверению:
  истекло — красный, действует — факт с датой, но не зелёный; у площадки те
  же числа; не водитель — прежняя причина словаря;
- (срез-84) строка «ПБ» — по противопожарным инструктажам и ПТМ человека,
  человек × вид по самой поздней дате действия: истёк — красный, действует —
  факт, но не зелёный; про средства защиты и тренировки площадки — ни слова;
  у площадки, где он единственный, — тот же инструктаж в просрочке.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.disciplines import DISCIPLINE_TITLES, Discipline
from app.models.briefings import BriefingEntry, BriefingJournal
from app.models.master_data import EmploymentStatus, Person, Site, Workplace
from app.models.medical import MedicalExam, MedicalExamKind, MedicalNorm
from app.models.models import Position, PPEIssue, PPEItem, PPENorm, RoleEnum
from app.models.risk import RiskHazard
from app.models.road_safety import Driver
from app.models.training import TrainingEnrollment, TrainingProgram
from app.services.employee_card import TERMINATED_REASON

NOW = datetime.now(tz=timezone.utc)
TODAY = date.today()


async def _card(async_client: AsyncClient, headers, person_id: str) -> dict:
    response = await async_client.get(f"/api/v1/employees/{person_id}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def _row(section: dict, discipline: str) -> dict:
    return next(r for r in section["rows"] if r["discipline"] == discipline)


#: Пять дисциплин Доп. №1 — продаваемые модули; по умолчанию у арендатора
#: теста они НЕ выданы (BIZ-61), и карточка их не показывает (срез-54).
DISCIPLINE_MODULES = (
    "fire_safety",
    "industrial_safety",
    "ecology",
    "civil_defense",
    "road_safety",
)


@pytest.fixture()
async def welder(sessionmaker, data_factory):
    """Сварщик на площадке: норма медосмотра без экзамена, норма каски с выдачей,
    одно просроченное обучение."""

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        # Редакция «всё включено»: иначе на карточке остались бы три дисциплины ядра.
        await data_factory.set_modules(session, tenant.id, DISCIPLINE_MODULES, on=True)
        company = await data_factory.create_company(tenant=tenant, name="АКМЕ", session=session)
        position = Position(tenant_id=tenant.id, company_id=company.id, name="Сварщик")
        hazard = RiskHazard(tenant_id=tenant.id, code="height", title="Работы на высоте")
        helmet = PPEItem(tenant_id=tenant.id, name="Каска защитная", default_wear_days=730)
        site = Site(tenant_id=tenant.id, company_id=company.id, name="Цех №1")
        program = TrainingProgram(
            tenant_id=tenant.id, code="ПРГ-1", title="Программа 46н", category="ot", kind="program"
        )
        session.add_all([position, hazard, helmet, site, program])
        await session.flush()
        workplace = Workplace(
            tenant_id=tenant.id, company_id=company.id, site_id=site.id, name="Пост сварки"
        )
        session.add(workplace)
        session.add_all(
            [
                MedicalNorm(
                    tenant_id=tenant.id,
                    position_id=position.id,
                    exam_kind=MedicalExamKind.PERIODIC,
                    interval_days=365,
                ),
                PPENorm(
                    tenant_id=tenant.id,
                    position_id=position.id,
                    hazard_id=hazard.id,
                    item_id=helmet.id,
                    item_name=helmet.name,
                    quantity=1,
                    interval_days=730,
                ),
            ]
        )
        await session.flush()
        person = await data_factory.create_person(
            tenant=tenant,
            company=company,
            last_name="Сварщиков",
            position_id=position.id,
            workplace_id=workplace.id,
            session=session,
        )
        session.add_all(
            [
                PPEIssue(
                    tenant_id=tenant.id,
                    person_id=person.id,
                    item_id=helmet.id,
                    item_name=helmet.name,
                    quantity=1,
                    issued_at=NOW - timedelta(days=10),
                    expires_at=NOW + timedelta(days=400),
                    status="issued",
                ),
                TrainingEnrollment(
                    tenant_id=tenant.id,
                    training_program_id=program.id,
                    person_id=person.id,
                    status="assigned",
                    due_at=NOW - timedelta(days=3),
                ),
            ]
        )
        await session.commit()
        return tenant, str(person.id), str(site.id)


@pytest.mark.anyio
class TestEmployeeCardDisciplines:
    async def test_строка_на_каждую_дисциплину_и_те_же_числа_что_у_площадки(
        self, async_client: AsyncClient, make_auth_headers, welder
    ) -> None:
        _tenant, person_id, site_id = welder
        headers = await make_auth_headers(RoleEnum.ADMIN)

        section = (await _card(async_client, headers, person_id))["disciplines"]
        site = (await async_client.get(f"/api/v1/sites/{site_id}/overview", headers=headers)).json()

        # все дисциплины словаря, в его порядке, его словами
        assert [r["discipline"] for r in section["rows"]] == [d.value for d in Discipline]
        for row in section["rows"]:
            assert row["title"] == DISCIPLINE_TITLES[Discipline(row["discipline"])]
        medical = _row(section, "medical")
        assert medical["light"] == "red"
        assert medical["required"] == 1 and medical["missing"] == 1
        assert "не оформлено вовсе: 1" in medical["reason"]
        ppe = _row(section, "ppe")
        assert ppe["light"] == "green"
        assert ppe["required"] == 1
        training = _row(section, "training")
        assert training["light"] == "red"
        assert "Просрочено назначенное обучение: 1" in training["reason"]
        assert _row(section, "fire_safety")["light"] == "not_measured"
        assert section["overall"] == "red"
        assert section["note"] is None
        assert section["not_applicable"] is None
        # человек на площадке один — карточка площадки считает то же самое
        site_rows = {r["discipline"]: r for r in site["disciplines"]}
        for code in ("medical", "ppe", "training"):
            mine, theirs = _row(section, code), site_rows[code]
            assert (mine["light"], mine["required"], mine["missing"], mine["lapsed"]) == (
                theirs["light"],
                theirs["required"],
                theirs["missing"],
                theirs["lapsed"],
            ), code

    async def test_зелёные_измеримые_дают_зелёный_итог_несмотря_на_неизмеримые(
        self, async_client: AsyncClient, make_auth_headers, welder, sessionmaker
    ) -> None:
        tenant, person_id, _ = welder
        async with sessionmaker() as session:
            session.add(
                MedicalExam(
                    tenant_id=tenant.id,
                    person_id=person_id,
                    exam_type="периодический",
                    exam_kind=MedicalExamKind.PERIODIC,
                    exam_date=TODAY - timedelta(days=30),
                    valid_until=TODAY + timedelta(days=300),
                )
            )
            enrollment = (
                await session.execute(
                    select(TrainingEnrollment).where(TrainingEnrollment.person_id == person_id)
                )
            ).scalar_one()
            enrollment.status = "completed"
            await session.commit()
        headers = await make_auth_headers(RoleEnum.ADMIN)

        section = (await _card(async_client, headers, person_id))["disciplines"]

        assert _row(section, "medical")["light"] == "green"
        assert _row(section, "ppe")["light"] == "green"
        # обучение без просрочек — «эталон не задан», а не зелёный
        assert _row(section, "training")["light"] == "not_measured"
        assert section["overall"] == "green"

    async def test_удостоверение_водителя_красит_бдд_и_площадка_считает_так_же(
        self, async_client: AsyncClient, make_auth_headers, welder, sessionmaker
    ) -> None:
        """Срез-64: у допущенного водителя БДД — по удостоверению.

        Истекло — красный (как просрочка обучения). Площадка, где этот человек
        единственный, показывает те же числа: правила одни. Не водитель —
        прежняя причина словаря, слово в слово.
        """

        from app.core.disciplines import UNMEASURED_DISCIPLINES

        tenant, person_id, site_id = welder
        headers = await make_auth_headers(RoleEnum.ADMIN)

        before = (await _card(async_client, headers, person_id))["disciplines"]
        assert _row(before, "road_safety")["light"] == "not_measured"
        assert (
            _row(before, "road_safety")["reason"] == UNMEASURED_DISCIPLINES[Discipline.ROAD_SAFETY]
        )

        async with sessionmaker() as session:
            session.add(
                Driver(
                    tenant_id=tenant.id,
                    person_id=person_id,
                    license_number="77 АА 000001",
                    categories=["B"],
                    license_due=TODAY - timedelta(days=2),
                    status="admitted",
                )
            )
            await session.commit()

        section = (await _card(async_client, headers, person_id))["disciplines"]
        site = (await async_client.get(f"/api/v1/sites/{site_id}/overview", headers=headers)).json()

        row = _row(section, "road_safety")
        assert row["light"] == "red"
        assert row["reason"] == "Истекло водительское удостоверение: 1"
        assert row["required"] == 1 and row["lapsed"] == 1
        theirs = next(r for r in site["disciplines"] if r["discipline"] == "road_safety")
        assert (theirs["light"], theirs["required"], theirs["lapsed"]) == ("red", 1, 1)

    async def test_истёкший_птм_красит_пб_человека_и_площадка_считает_так_же(
        self, async_client: AsyncClient, make_auth_headers, welder, sessionmaker
    ) -> None:
        """Срез-84: ПБ на карточке человека — его инструктажи, без объектов."""

        from app.core.discipline_status import FIRE_SAFETY_PERSON_REASON

        tenant, person_id, site_id = welder
        headers = await make_auth_headers(RoleEnum.ADMIN)

        before = _row((await _card(async_client, headers, person_id))["disciplines"], "fire_safety")
        assert before["light"] == "not_measured"
        assert before["reason"] == FIRE_SAFETY_PERSON_REASON

        async with sessionmaker() as session:
            journal = BriefingJournal(
                tenant_id=tenant.id, code="J-FIRE", title="Журнал ПБ", journal_type="fire"
            )
            session.add(journal)
            await session.flush()
            for briefing_type, days_ago, valid_days in (
                # ПТМ истёк — просрочка
                ("fire_ptm", 400, -35),
                # повторный: старая запись перекрыта свежей — действует
                ("fire_repeat", 400, -220),
                ("fire_repeat", 10, 170),
            ):
                session.add(
                    BriefingEntry(
                        tenant_id=tenant.id,
                        briefing_journal_id=journal.id,
                        person_id=person_id,
                        briefing_type=briefing_type,
                        briefing_date=NOW - timedelta(days=days_ago),
                        valid_until=NOW + timedelta(days=valid_days),
                        status="completed",
                    )
                )
            await session.commit()

        section = (await _card(async_client, headers, person_id))["disciplines"]
        site = (await async_client.get(f"/api/v1/sites/{site_id}/overview", headers=headers)).json()

        row = _row(section, "fire_safety")
        assert row["light"] == "red"
        assert row["reason"] == (
            "Просрочено по ПБ — противопожарные инструктажи: 1; "
            "противопожарных инструктажей действует: 1"
        )
        assert row["required"] == 2 and row["lapsed"] == 1
        assert section["overall"] == "red"
        theirs = next(r for r in site["disciplines"] if r["discipline"] == "fire_safety")
        assert (theirs["light"], theirs["required"], theirs["lapsed"]) == ("red", 2, 1)
        # у площадки — ещё и факты объекта, у человека их нет
        assert "тренировок" in theirs["reason"] and "тренировок" not in row["reason"]

    async def test_действующее_удостоверение_это_факт_а_не_зелёный(
        self, async_client: AsyncClient, make_auth_headers, welder, sessionmaker
    ) -> None:
        """Отстранённый водитель не считается вовсе; действующее удостоверение
        называется с датой, но цвет — «не измеряется»: эталона БДД нет."""

        tenant, person_id, _ = welder
        headers = await make_auth_headers(RoleEnum.ADMIN)
        due = TODAY + timedelta(days=200)

        async with sessionmaker() as session:
            driver = Driver(
                tenant_id=tenant.id,
                person_id=person_id,
                license_number="77 АА 000002",
                categories=["B"],
                license_due=due,
                status="suspended",
            )
            session.add(driver)
            await session.commit()
            driver_id = driver.id

        suspended = (await _card(async_client, headers, person_id))["disciplines"]
        assert _row(suspended, "road_safety")["required"] == 0

        async with sessionmaker() as session:
            record = await session.get(Driver, driver_id)
            record.status = "admitted"
            await session.commit()

        row = _row((await _card(async_client, headers, person_id))["disciplines"], "road_safety")
        assert row["light"] == "not_measured"
        assert row["reason"].startswith(
            f"Водительское удостоверение действует (до {due.strftime('%d.%m.%Y')}). "
        )
        assert "эталон" in row["reason"].lower()

    async def test_эталон_не_задан_говорит_про_должность_человека(
        self, async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory
    ) -> None:
        async with sessionmaker() as session:
            tenant = await data_factory.ensure_tenant(session=session)
            company = await data_factory.create_company(tenant=tenant, session=session)
            position = Position(tenant_id=tenant.id, company_id=company.id, name="Клерк")
            session.add(position)
            await session.flush()
            with_position = await data_factory.create_person(
                tenant=tenant,
                company=company,
                last_name="Клерков",
                position_id=position.id,
                session=session,
            )
            without_position = await data_factory.create_person(
                tenant=tenant, company=company, last_name="Безработных", session=session
            )
            await session.commit()
            with_id, without_id = str(with_position.id), str(without_position.id)
        headers = await make_auth_headers(RoleEnum.ADMIN)

        clerk = (await _card(async_client, headers, with_id))["disciplines"]
        nobody = (await _card(async_client, headers, without_id))["disciplines"]

        assert _row(clerk, "medical")["light"] == "not_measured"
        assert _row(clerk, "medical")["reason"] == "Эталон не задан: у должности нет норм"
        assert _row(clerk, "ppe")["reason"] == "Эталон не задан: у должности нет норм"
        assert _row(nobody, "medical")["reason"] == "Эталон не задан: должность не указана"
        assert clerk["overall"] == "not_measured"

    async def test_уволенный_не_красится(
        self, async_client: AsyncClient, make_auth_headers, welder, sessionmaker
    ) -> None:
        tenant, person_id, _ = welder
        async with sessionmaker() as session:
            person = await session.get(Person, person_id)
            person.employment_status = EmploymentStatus.TERMINATED
            await session.commit()
        headers = await make_auth_headers(RoleEnum.ADMIN)

        section = (await _card(async_client, headers, person_id))["disciplines"]

        assert section["overall"] == "not_measured"
        assert section["note"] == TERMINATED_REASON
        assert len(section["rows"]) == len(Discipline)
        assert all(r["light"] == "not_measured" for r in section["rows"])
        assert all(r["reason"] == TERMINATED_REASON for r in section["rows"])

    async def test_дисциплины_вне_редакции_скрыты_и_названы_фразой(
        self, async_client: AsyncClient, make_auth_headers, welder, sessionmaker, data_factory
    ) -> None:
        """Приёмка §58.3: дисциплины включаются флагами; скрытое не молчит (срез-54)."""

        tenant, person_id, site_id = welder
        async with sessionmaker() as session:
            await data_factory.set_modules(
                session, tenant.id, ("ecology", "civil_defense", "road_safety"), on=False
            )
            await session.commit()
        headers = await make_auth_headers(RoleEnum.ADMIN)

        section = (await _card(async_client, headers, person_id))["disciplines"]
        site = (await async_client.get(f"/api/v1/sites/{site_id}/overview", headers=headers)).json()

        assert [r["discipline"] for r in section["rows"]] == [
            "medical",
            "ppe",
            "training",
            "fire_safety",
            "industrial_safety",
        ]
        assert section["overall"] == "red"
        assert section["not_applicable"] == (
            "Вне редакции арендатора (модуль не выдан или выключен): Экология, ГО и ЧС, БДД"
        )
        # площадка того же арендатора скрывает то же самое — одно правило на обе карточки
        assert [r["discipline"] for r in site["disciplines"]] == [
            r["discipline"] for r in section["rows"]
        ]

    async def test_уволенный_вне_редакции_тоже_не_видит_скрытого(
        self, async_client: AsyncClient, make_auth_headers, welder, sessionmaker, data_factory
    ) -> None:
        tenant, person_id, _ = welder
        async with sessionmaker() as session:
            await data_factory.set_modules(session, tenant.id, ("ecology",), on=False)
            person = await session.get(Person, person_id)
            person.employment_status = EmploymentStatus.TERMINATED
            await session.commit()
        headers = await make_auth_headers(RoleEnum.ADMIN)

        section = (await _card(async_client, headers, person_id))["disciplines"]

        assert len(section["rows"]) == len(Discipline) - 1
        assert "ecology" not in {r["discipline"] for r in section["rows"]}
        assert section["note"] == TERMINATED_REASON
        assert section["not_applicable"].endswith(": Экология")
