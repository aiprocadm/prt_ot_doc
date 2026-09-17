"""Стажировка на рабочем месте (ядро; требование Доп. №1 разд. 56.2, срез-7).

Требование пришло из БДД: «Инструктажи и СТАЖИРОВКИ водителей, проверки знаний
ПДД/БДД». Инструктажи закрыл срез-5, проверки знаний — срез-6, здесь —
стажировки. Пункт разд. 56.2 закрывается целиком.

СВЕРКА нашла ГЛАВНОЕ — И ЭТО ПРОТИВ ОЖИДАНИЯ:

**Стажировка не водительская.** Требование стоит в разделе про БДД, и напрашивалось
завести ``road_internship`` внутри контура. Но комплект документов печатает
«Стажировка: {{ data.internship_days }} смен» в ПЕРВИЧНОМ ИНСТРУКТАЖЕ НОВОГО
РАБОТНИКА (``modules/packs/definitions.py``) — то есть по охране труда и любому
рабочему. Заведи реестр внутри БДД — и через срез появилась бы стажировка
стропальщика, а с ней второй реестр одного и того же. В базовом ТЗ слова
«стажировка» нет вовсе: требование единственный раз названо в 56.2, но вещь
общая.

Поэтому: ОБЩАЯ сущность в ядре + разметка дисциплиной. Это ЧЕТВЁРТЫЙ случай
одного приёма, и потому он канон: виды инструктажа (54.1), области аттестации
(54.2 и 56.2), дисциплина курса (56.1) и теперь стажировка.

Ещё сверка подтвердила: **учёта стажировок не было НИКАКОГО** — только поле
``internship_days`` в шаблоне документа. Бумага печатается, за ней ничего.

Решения:

* **сущность в ядре, а не в БДД** — довод выше;
* **люди не дублируются**: и стажёр, и наставник — ядровые ``Person``;
* **наставник НЕОБЯЗАТЕЛЕН** (в приказе его называют позже), но **не может
  быть стажёром**: стажировка «сам у себя» это либо опечатка, либо приписка, и
  в обоих случаях означает, что стажировки не было;
* **смены хранятся числами, а недобор СЧИТАЕТСЯ**: «завершена, а смен меньше
  плана» — формально закрытая стажировка, которой по сменам не было. Это самое
  ценное, что тут можно показать;
* **пустая дисциплина законна** и означает «не размечено», а НЕ «охрана
  труда» (прецедент дисциплины курса в 56.1).

ГРАНИЦА: платформа НЕ решает, нужна ли стажировка и сколько смен она длится —
это следует из профессии, стажа работника и локального приказа. Недобор — ФАКТ
расхождения плана и факта, а не вердикт «допуск незаконен». Полей «требуется ли
стажировка», «достаточно ли смен» и «допущен ли к самостоятельной работе» нет
ни в записи, ни в сводке.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from sqlalchemy import select

from app.core.disciplines import Discipline
from app.models.feature import Feature, FeatureEnablement
from app.models.master_data import Company, Person
from app.models.models import Tenant
from app.models.training import INTERNSHIP_STATUSES

pytestmark = pytest.mark.anyio

_API = "/api/v1/internships"
_ROAD = "/api/v1/road-safety"


async def _grant(sessionmaker, code: str, on: bool = True) -> None:
    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
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
            session.add(FeatureEnablement(tenant_id=tenant.id, feature_id=feature.id, on=on))
        else:
            grant.on = on
        await session.commit()


async def _person(sessionmaker, last_name: str) -> str:
    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        company = (
            await session.execute(select(Company).where(Company.tenant_id == tenant.id).limit(1))
        ).scalar_one_or_none()
        if company is None:
            company = Company(tenant_id=str(tenant.id), name="ООО «Тест»")
            session.add(company)
            await session.flush()
        person = Person(
            tenant_id=str(tenant.id),
            company_id=company.id,
            last_name=last_name,
            first_name="Пётр",
            middle_name="Иванович",
        )
        session.add(person)
        await session.commit()
        return person.id


async def _internship(
    async_client,
    headers,
    person_id: str,
    *,
    mentor_id: str | None = None,
    discipline: str | None = None,
    planned: int = 4,
    completed: int = 0,
    status: str = "planned",
    subject: str | None = "автобус категории D",
    expect: int = 201,
) -> dict:
    payload: dict[str, object] = {
        "person_id": person_id,
        "planned_shifts": planned,
        "completed_shifts": completed,
        "status": status,
    }
    if mentor_id is not None:
        payload["mentor_person_id"] = mentor_id
    if discipline is not None:
        payload["discipline"] = discipline
    if subject is not None:
        payload["subject"] = subject
    response = await async_client.post(_API, json=payload, headers=headers)
    assert response.status_code == expect, response.text
    return response.json()


class TestСущностьВЯдре:
    async def test_стажировка_заводится_ядровой_ручкой(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Ручка ЯДРОВАЯ, а не в контуре БДД: стажировка не водительская."""

        headers = await make_auth_headers()
        trainee = await _person(sessionmaker, "Стажёров")
        mentor = await _person(sessionmaker, "Наставников")
        body = await _internship(
            async_client,
            headers,
            trainee,
            mentor_id=mentor,
            discipline=Discipline.ROAD_SAFETY.value,
        )
        assert body["person_name"] == "Стажёров Пётр Иванович"
        assert body["mentor_name"] == "Наставников Пётр Иванович"
        assert body["discipline_label"] == "БДД"
        assert body["status_label"] == "Назначена"

    async def test_стажировка_доступна_без_модуля_бдд(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Сторож против запирания общего в дисциплину.

        Стажировка нужна любому рабочему, и закрыть её модулем БДД значило бы
        отобрать её у тех, кто транспорт не эксплуатирует.
        """

        headers = await make_auth_headers()
        await _grant(sessionmaker, "road_safety", on=False)
        trainee = await _person(sessionmaker, "Стропальщиков")
        body = await _internship(async_client, headers, trainee, subject="стропальные работы")
        assert body["subject"] == "стропальные работы"

    async def test_пустая_дисциплина_законна(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Пусто — «не размечено», а НЕ «охрана труда» (прецедент 56.1)."""

        headers = await make_auth_headers()
        trainee = await _person(sessionmaker, "Неразмеченов")
        body = await _internship(async_client, headers, trainee)
        assert body["discipline"] is None
        assert body["discipline_label"] is None

    async def test_неизвестная_дисциплина_отвергается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        trainee = await _person(sessionmaker, "Ошибкин")
        await _internship(async_client, headers, trainee, discipline="бдд", expect=422)

    async def test_неизвестное_состояние_отвергается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        trainee = await _person(sessionmaker, "Состояньев")
        await _internship(async_client, headers, trainee, status="идёт", expect=422)


class TestЛюдиНеДублируются:
    async def test_наставник_не_может_быть_стажёром(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Стажировка «сам у себя» означает, что стажировки не было.

        Это либо опечатка, либо приписка — и в обоих случаях запись врёт о
        главном: что человека кто-то учил.
        """

        headers = await make_auth_headers()
        trainee = await _person(sessionmaker, "Одиноков")
        await _internship(async_client, headers, trainee, mentor_id=trainee, expect=422)

    async def test_наставник_необязателен(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """В приказе наставника называют позже — требовать сразу значило бы
        заставлять выдумывать."""

        headers = await make_auth_headers()
        trainee = await _person(sessionmaker, "Безнаставников")
        body = await _internship(async_client, headers, trainee)
        assert body["mentor_person_id"] is None
        assert body["mentor_name"] is None

    async def test_чужого_человека_нет(self, async_client, make_auth_headers, sessionmaker) -> None:
        headers = await make_auth_headers()
        response = await async_client.post(
            _API,
            json={"person_id": "нет-такого", "planned_shifts": 2},
            headers=headers,
        )
        assert response.status_code == 404


class TestНедоборСмен:
    """Самое ценное: формально закрытая стажировка, которой по сменам не было."""

    async def test_недобор_считается_а_не_хранится(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        trainee = await _person(sessionmaker, "Недоборов")
        body = await _internship(
            async_client, headers, trainee, planned=8, completed=3, status="completed"
        )
        assert body["shifts_remaining"] == 5
        assert body["completed_short"] is True

    async def test_незавершённая_недобором_не_считается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Идущая стажировка с неполными сменами — это норма, а не нарушение.

        Считать её недобором значило бы каждый день кричать о нарушениях,
        которых нет (тот же довод, что у свежего путевого листа в срезе-3).
        """

        headers = await make_auth_headers()
        trainee = await _person(sessionmaker, "Идущев")
        body = await _internship(
            async_client, headers, trainee, planned=8, completed=3, status="in_progress"
        )
        assert body["shifts_remaining"] == 5
        assert body["completed_short"] is False

    async def test_недобор_пересчитывается_после_правки(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        trainee = await _person(sessionmaker, "Правков")
        body = await _internship(
            async_client, headers, trainee, planned=8, completed=3, status="completed"
        )
        assert body["completed_short"] is True
        response = await async_client.patch(
            f"{_API}/{body['id']}", json={"completed_shifts": 8}, headers=headers
        )
        assert response.status_code == 200, response.text
        assert response.json()["completed_short"] is False
        assert response.json()["shifts_remaining"] == 0

    async def test_недобор_снаружи_не_записывается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Сторож: прими ручка ``completed_short`` — появилось бы второе место
        правды, расходящееся со сменами."""

        headers = await make_auth_headers()
        trainee = await _person(sessionmaker, "Сторожев")
        body = await _internship(
            async_client, headers, trainee, planned=8, completed=8, status="completed"
        )
        response = await async_client.patch(
            f"{_API}/{body['id']}", json={"completed_short": True}, headers=headers
        )
        assert response.status_code == 200, response.text
        assert response.json()["completed_short"] is False

    async def test_отрицательные_смены_отвергаются(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        trainee = await _person(sessionmaker, "Минусов")
        await _internship(async_client, headers, trainee, completed=-1, expect=422)

    async def test_перевыполнение_не_даёт_отрицательного_остатка(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Смен больше плана — законно; «осталось минус два» — бессмыслица."""

        headers = await make_auth_headers()
        trainee = await _person(sessionmaker, "Перевыполнев")
        body = await _internship(
            async_client, headers, trainee, planned=4, completed=6, status="completed"
        )
        assert body["shifts_remaining"] == 0
        assert body["completed_short"] is False


class TestОтборИСводкаБДД:
    async def test_отбор_по_дисциплине(self, async_client, make_auth_headers, sessionmaker) -> None:
        headers = await make_auth_headers()
        driver = await _person(sessionmaker, "Водителев")
        welder = await _person(sessionmaker, "Сварщиков")
        await _internship(async_client, headers, driver, discipline=Discipline.ROAD_SAFETY.value)
        await _internship(async_client, headers, welder)
        response = await async_client.get(
            _API, params={"discipline": Discipline.ROAD_SAFETY.value}, headers=headers
        )
        assert response.status_code == 200, response.text
        names = [row["person_name"] for row in response.json()["items"]]
        assert names == ["Водителев Пётр Иванович"]

    async def test_сводка_бдд_считает_свои_стажировки(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker, "road_safety")
        driver = await _person(sessionmaker, "Водителев")
        second = await _person(sessionmaker, "Второв")
        await _internship(
            async_client,
            headers,
            driver,
            discipline=Discipline.ROAD_SAFETY.value,
            status="in_progress",
        )
        await _internship(
            async_client,
            headers,
            second,
            discipline=Discipline.ROAD_SAFETY.value,
            planned=8,
            completed=2,
            status="completed",
        )
        body = (await async_client.get(f"{_ROAD}/readiness", headers=headers)).json()
        assert body["internships_total"] == 2
        assert body["internships_in_progress"] == 1
        assert body["internships_completed_short"] == 1

    async def test_чужие_стажировки_в_сводку_бдд_не_попадают(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Сторож: без отбора по дисциплине сюда попали бы все стажировки."""

        headers = await make_auth_headers()
        await _grant(sessionmaker, "road_safety")
        welder = await _person(sessionmaker, "Сварщиков")
        unmarked = await _person(sessionmaker, "Неразмеченов")
        await _internship(async_client, headers, welder, discipline=Discipline.TRAINING.value)
        await _internship(async_client, headers, unmarked)
        body = (await async_client.get(f"{_ROAD}/readiness", headers=headers)).json()
        assert body["internships_total"] == 0

    async def test_вердикта_о_необходимости_стажировки_нет(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """ГРАНИЦА: нужна ли стажировка и сколько смен — не решение платформы."""

        headers = await make_auth_headers()
        await _grant(sessionmaker, "road_safety")
        body = (await async_client.get(f"{_ROAD}/readiness", headers=headers)).json()
        assert not any(
            key in body
            for key in (
                "internships_required",
                "internships_missing",
                "admission_valid",
            )
        )


class TestСводкаЯдра:
    """Сводка ОБЩЕГО экрана стажировок (срез: экран, `GET /internships/summary`).

    До этого среза стажировки считала только сводка БДД — и только СВОИ (по
    разметке дисциплиной). У общего экрана числа должны сходиться по ВСЕМ
    записям арендатора, включая неразмеченные, и считаться В БАЗЕ: первая
    страница списка на экране — не основание для плитки «всего».
    """

    async def test_сводка_считает_все_дисциплины(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        driver = await _person(sessionmaker, "Водителев")
        welder = await _person(sessionmaker, "Сварщиков")
        unmarked = await _person(sessionmaker, "Неразмеченов")
        await _internship(
            async_client,
            headers,
            driver,
            discipline=Discipline.ROAD_SAFETY.value,
            status="in_progress",
        )
        await _internship(
            async_client,
            headers,
            welder,
            discipline=Discipline.TRAINING.value,
            planned=8,
            completed=2,
            status="completed",
        )
        await _internship(async_client, headers, unmarked)
        response = await async_client.get(f"{_API}/summary", headers=headers)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["total"] == 3
        assert body["by_status"] == {
            "planned": 1,
            "in_progress": 1,
            "completed": 1,
            "cancelled": 0,
        }
        assert body["completed_short"] == 1

    async def test_недобор_только_у_завершённых(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Идущая с 0 из 4 смен — не недобор: она ещё не закрыта."""

        headers = await make_auth_headers()
        trainee = await _person(sessionmaker, "Стажёров")
        await _internship(
            async_client, headers, trainee, planned=4, completed=0, status="in_progress"
        )
        body = (await async_client.get(f"{_API}/summary", headers=headers)).json()
        assert body["total"] == 1
        assert body["completed_short"] == 0

    async def test_активная_без_наставника_названа_отдельно(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Назначена или идёт, а наставника нет — ДЫРА В ДАННЫХ, не нарушение.

        В приказе наставника иногда называют позже, поэтому поле необязательно;
        но стажировка без наставника — это стажировка, у которой некому
        подтвердить смены. Завершённые и отменённые сюда не входят: у них
        наставника уже не назначат.
        """

        headers = await make_auth_headers()
        mentor = await _person(sessionmaker, "Наставников")
        planned_alone = await _person(sessionmaker, "Одинокин")
        running_alone = await _person(sessionmaker, "Бегущин")
        running_with = await _person(sessionmaker, "Сопровождаев")
        done_alone = await _person(sessionmaker, "Завершилов")
        await _internship(async_client, headers, planned_alone)
        await _internship(async_client, headers, running_alone, status="in_progress")
        await _internship(
            async_client, headers, running_with, mentor_id=mentor, status="in_progress"
        )
        await _internship(
            async_client, headers, done_alone, planned=2, completed=2, status="completed"
        )
        body = (await async_client.get(f"{_API}/summary", headers=headers)).json()
        assert body["active_without_mentor"] == 2

    async def test_вердикта_в_сводке_нет(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """ГРАНИЦА: сводка называет факты, а не решает, законен ли допуск."""

        headers = await make_auth_headers()
        body = (await async_client.get(f"{_API}/summary", headers=headers)).json()
        assert body["total"] == 0
        assert not any(
            key in body for key in ("required", "missing", "admission_valid", "shifts_enough")
        )


class TestОбщийЭкран:
    """Срез-41: экран у стажировок ОБЩИЙ, словарь состояний на фронте — руками."""

    def test_фронт_знает_те_же_состояния(self) -> None:
        """Сторож против дрейфа: словарь состояний на фронте написан руками.

        Тот же класс, что словарь дисциплин в ``training.ts``: не обнови
        фронт — состояние нельзя будет ни выбрать в форме, ни отфильтровать.
        """

        page = Path(__file__).resolve().parents[1] / "frontend" / "src" / "api" / "internships.ts"
        text = page.read_text(encoding="utf-8")
        block = re.search(
            r"INTERNSHIP_STATUS_TITLES:\s*Record<string,\s*string>\s*=\s*\{(.*?)\}",
            text,
            re.S,
        )
        assert block is not None, "не нашёлся словарь состояний на фронте"
        front = dict(re.findall(r'^\s*([a-z_]+):\s*"([^"]*)"', block.group(1), re.M))
        assert front == INTERNSHIP_STATUSES, sorted(
            set(front.items()) ^ set(INTERNSHIP_STATUSES.items())
        )
