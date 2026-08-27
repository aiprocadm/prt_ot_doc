"""Контур ГО и ЧС срез-2 (Доп. №1 разд. 56.1): учения и тренировки.

Требование: «Обучение и учения: программы обучения по ГО и ЧС, курсовое
обучение, план-график учений и тренировок, журналы». Срез закрывает
план-график учений с протоколами (журнал проведённых — это и есть реестр с
фактическими датами); программы обучения и курсовое обучение — следующий срез
(они опираются на контур обучения ядра, а не на свой реестр).

СВЕРКА нашла два расхождения:

1. **Учений ГО не было.** Срез-1 завёл формирования, но вопрос «когда это
   формирование в последний раз отрабатывало задачи и не просрочено ли
   очередное учение» не имел ответа в данных. Дисциплина умела ВЫПУСТИТЬ
   документ комплектом GOCHS_BASE, но не умела УЧЕСТЬ проведённое — ровно та
   же дыра, что закрывал срез тренировок ПБ (54.1).
2. **Контур комиссий существует, но КЧС и эвакокомиссии в нём НЕТ.**
   ``CommitteeKind`` (модуль committees, составы, протоколы, решения, голоса)
   знает комитет по ОТ, комитет по ПБ, комиссию по обучению и комиссию по
   расследованию — а комиссии по чрезвычайным ситуациям и эвакокомиссии в
   закрытом словаре нет. Требование 56.1 «Комиссии: КЧС и ПБ, эвакокомиссия»
   упирается ровно в два значения словаря, а НЕ в новый контур: дублировать
   составы и протоколы было бы нарушением принципа мультидисциплинарности.
   Зафиксировано в матрице как следующий точный шаг.

Решения:

* **своя таблица учений, а не переиспользование тренировок ПБ**: у учения ГО
  есть то, чего у пожарной тренировки не бывает — задействованное
  ФОРМИРОВАНИЕ (срез-1). Виды тоже разные: командно-штабное учение и
  тренировка по эвакуации — разные основания, участники и органы;
* **правила протокола — те же, что в ПБ** (осознанное единообразие): дата
  проведения не в будущем, проведено → есть результат, результат → есть дата;
* **статус считается ПРИ ЧТЕНИИ**: срок наступает сам, без запроса на
  изменение;
* **формирование необязательно**: объектовая тренировка проводится всем
  персоналом, а не силами формирования — требовать привязку значило бы
  выдумывать связь.

ГРАНИЦА: платформа НЕ назначает периодичность учений. Она установлена
постановлением Правительства и зависит от категории организации по ГО;
полей «требуемая периодичность» и «следующее учение» в ответах нет — только
внесённый план-график.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.models.feature import Feature, FeatureEnablement
from app.models.models import Tenant

pytestmark = pytest.mark.anyio

_API = "/api/v1/civil-defense"


async def _grant(sessionmaker, code: str = "civil_defense", on: bool = True) -> None:
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


async def _formation(async_client, headers, name: str = "Звено пожаротушения") -> str:
    response = await async_client.post(
        f"{_API}/formations",
        json={"name": name, "kind": "nasf"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _drill(
    async_client,
    headers,
    *,
    kind: str = "command_staff",
    title: str = "Командно-штабное учение по ликвидации ЧС",
    planned_on: date | None = None,
    formation_id: str | None = None,
) -> dict:
    payload: dict[str, object] = {
        "kind": kind,
        "title": title,
        "planned_on": str(planned_on or (date.today() + timedelta(days=30))),
    }
    if formation_id is not None:
        payload["formation_id"] = formation_id
    response = await async_client.post(f"{_API}/drills", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


class TestПланГрафикУчений:
    async def test_без_выдачи_модуль_невидим(
        self, async_client, make_auth_headers
    ) -> None:
        headers = await make_auth_headers()
        response = await async_client.get(f"{_API}/drills", headers=headers)
        assert response.status_code == 404

    async def test_учение_заводится_запланированным_и_вид_словами(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Учение рождается ЗАПЛАНИРОВАННЫМ — иначе плана-графика нет."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        body = await _drill(async_client, headers)
        assert body["kind_label"] == "Командно-штабное учение"
        assert body["status"] == "planned"
        assert body["status_label"] == "Запланировано"
        assert body["held_on"] is None

    async def test_неизвестный_вид_отвергается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        response = await async_client.post(
            f"{_API}/drills",
            json={
                "kind": "пожарная",
                "title": "Что-то",
                "planned_on": str(date.today()),
            },
            headers=headers,
        )
        assert response.status_code == 422, response.text

    async def test_просроченное_учение_названо_словами(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        await _drill(
            async_client,
            headers,
            title="Объектовая тренировка",
            kind="facility_training",
            planned_on=date.today() - timedelta(days=10),
        )
        listed = await async_client.get(f"{_API}/drills", headers=headers)
        item = listed.json()["items"][0]
        assert item["status"] == "overdue"
        assert item["status_label"] == "Просрочено"


class TestПротоколУчения:
    async def test_проведённое_учение_с_результатом(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        drill = await _drill(
            async_client, headers, planned_on=date.today() - timedelta(days=5)
        )
        held = await async_client.patch(
            f"{_API}/drills/{drill['id']}",
            json={
                "held_on": str(date.today() - timedelta(days=5)),
                "outcome": "with_remarks",
                "participants": 24,
                "findings": "Задержка сбора формирования на 7 минут",
            },
            headers=headers,
        )
        assert held.status_code == 200, held.text
        body = held.json()
        assert body["status"] == "held"
        assert body["status_label"] == "Проведено"
        assert body["outcome_label"] == "Проведено с замечаниями"
        # Проведённое просрочкой НЕ считается, даже если план был в прошлом.
        assert body["status"] != "overdue"

    async def test_дата_проведения_в_будущем_отвергается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Это план, а не протокол."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        drill = await _drill(async_client, headers)
        response = await async_client.patch(
            f"{_API}/drills/{drill['id']}",
            json={
                "held_on": str(date.today() + timedelta(days=1)),
                "outcome": "passed",
            },
            headers=headers,
        )
        assert response.status_code == 422, response.text

    async def test_проведённое_без_результата_отвергается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Запись «провели» без оценки нечего анализировать."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        drill = await _drill(async_client, headers)
        response = await async_client.patch(
            f"{_API}/drills/{drill['id']}",
            json={"held_on": str(date.today())},
            headers=headers,
        )
        assert response.status_code == 422, response.text

    async def test_результат_без_даты_проведения_отвергается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Оценка без даты проведения — выдумка о событии, которого не было."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        drill = await _drill(async_client, headers)
        response = await async_client.patch(
            f"{_API}/drills/{drill['id']}",
            json={"outcome": "passed"},
            headers=headers,
        )
        assert response.status_code == 422, response.text

    async def test_неизвестный_результат_отвергается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        drill = await _drill(async_client, headers)
        response = await async_client.patch(
            f"{_API}/drills/{drill['id']}",
            json={"held_on": str(date.today()), "outcome": "хорошо"},
            headers=headers,
        )
        assert response.status_code == 422, response.text


class TestСвязьСФормированием:
    async def test_учение_привязывается_к_формированию_из_среза_1(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """То, чего нет у пожарной тренировки: силы, отрабатывающие задачи."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        formation_id = await _formation(async_client, headers, "Звено связи")
        body = await _drill(async_client, headers, formation_id=formation_id)
        assert body["formation_id"] == formation_id
        assert body["formation_name"] == "Звено связи"

    async def test_учение_без_формирования_принимается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Объектовая тренировка идёт всем персоналом, а не силами звена."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        body = await _drill(
            async_client, headers, kind="facility_training", title="Тренировка"
        )
        assert body["formation_id"] is None
        assert body["formation_name"] is None

    async def test_чужое_формирование_отвергается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        response = await async_client.post(
            f"{_API}/drills",
            json={
                "kind": "command_staff",
                "title": "Учение",
                "planned_on": str(date.today()),
                "formation_id": "00000000-0000-0000-0000-000000000000",
            },
            headers=headers,
        )
        assert response.status_code == 404, response.text


class TestЖурналСводкаИГраница:
    async def test_журнал_проведённых_фильтруется_отдельно(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """«Журнал» из ТЗ — это реестр с фактическими датами проведения."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        held = await _drill(
            async_client,
            headers,
            title="Проведённое учение",
            planned_on=date.today() - timedelta(days=20),
        )
        await async_client.patch(
            f"{_API}/drills/{held['id']}",
            json={"held_on": str(date.today() - timedelta(days=20)), "outcome": "passed"},
            headers=headers,
        )
        await _drill(async_client, headers, title="Запланированное учение")

        journal = await async_client.get(
            f"{_API}/drills", params={"status": "held"}, headers=headers
        )
        assert journal.status_code == 200, journal.text
        titles = [row["title"] for row in journal.json()["items"]]
        assert titles == ["Проведённое учение"]

    async def test_сводка_считает_просрочки_и_проведённые_за_год(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        overdue = await _drill(
            async_client,
            headers,
            title="Просроченное",
            planned_on=date.today() - timedelta(days=15),
        )
        assert overdue["status"] == "overdue"
        held = await _drill(
            async_client,
            headers,
            title="Проведённое",
            planned_on=date.today() - timedelta(days=40),
        )
        await async_client.patch(
            f"{_API}/drills/{held['id']}",
            json={"held_on": str(date.today() - timedelta(days=40)), "outcome": "passed"},
            headers=headers,
        )
        readiness = await async_client.get(f"{_API}/readiness", headers=headers)
        body = readiness.json()
        assert body["drills_total"] == 2
        assert body["drills_overdue"] == 1
        assert body["drills_held_this_year"] == 1

    async def test_платформа_не_назначает_периодичность_учений(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """ГРАНИЦА: периодичность установлена постановлением и категорией по ГО."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        body = await _drill(async_client, headers)
        forbidden = {
            "required_periodicity_months",
            "next_due_on",
            "drill_required",
            "recommended_kind",
        }
        assert forbidden.isdisjoint(body.keys())
        readiness = await async_client.get(f"{_API}/readiness", headers=headers)
        assert forbidden.isdisjoint(readiness.json().keys())

    async def test_чужое_учение_не_читается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        response = await async_client.patch(
            f"{_API}/drills/00000000-0000-0000-0000-000000000000",
            json={"title": "Чужое"},
            headers=headers,
        )
        assert response.status_code == 404, response.text
