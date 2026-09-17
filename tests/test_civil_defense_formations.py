"""Контур ГО и ЧС срез-1 (Доп. №1 разд. 56.1): силы и средства — НАСФ/НФГО.

Требование: «Силы и средства: НАСФ/НФГО (нештатные формирования), составы,
оснащение, СИЗ ГО, средства оповещения». Срез закрывает реестр формирований и
составы; отдельные реестры оснащения, СИЗ ГО и средств оповещения — следующие
срезы (им нужно формирование, которого до сих пор не существовало).

СВЕРКА. По разд. 56 в продукте не было НИЧЕГО, кроме словарной строки
дисциплины, комплекта документов GOCHS_BASE в фабрике и честной причины в
библиотеке правил («ни формирований, ни учений, ни планов»). Ни модуля, ни
моделей, ни экрана — ровно как экология до её среза-1.

Решения:

* **вид формирования — закрытый словарь из двух**: НАСФ (аварийно-спасательные)
  и НФГО (по обеспечению выполнения мероприятий ГО) — это деление установлено
  законом, третьего вида не бывает. Назначение (звено пожаротушения, пост РХН…)
  — свободная строка: профилей десятки, словарь в коде гарантированно отстанет;
* **состав — люди из ЯДРА** (принцип мультидисциплинарности, преамбула разд.
  54): формирование ссылается на Person, а не заводит своих «бойцов»;
* **вывод из состава — дата, а не удаление строки**: отчисленный остаётся в
  истории формирования; в численности считаются только действующие;
* **одна строка на пару «формирование + человек»**: повторное включение
  сбрасывает дату вывода, а не плодит дубли.

ГРАНИЦА: платформа НЕ решает, обязана ли организация создавать формирования и
сколько их нужно — это следует из категории организации по ГО и решений органа
управления ГОЧС. Полей «требуется формирований» и «недоукомплектовано» в
ответах нет: платформа показывает факты о внесённом.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select

from app.models.civil_defense import CD_FORMATION_KINDS
from app.models.feature import Feature, FeatureEnablement
from app.models.models import Company, Person, Tenant

pytestmark = pytest.mark.anyio

_API = "/api/v1/civil-defense"


_FRONTEND_CD_API = (
    Path(__file__).resolve().parents[1] / "frontend" / "src" / "api" / "civilDefense.ts"
)


def _front_map(name: str) -> dict[str, str]:
    """Читает map подписей из ``frontend/src/api/civilDefense.ts``."""

    text = _FRONTEND_CD_API.read_text(encoding="utf-8")
    block = re.search(rf"{name}:\s*Record<[^>]+>\s*=\s*\{{(.*?)\n\}}", text, re.S)
    assert block is not None, f"не нашёлся map {name}"
    return dict(re.findall(r'^\s*([A-Za-z_0-9]+):\s*"([^"]+)"', block.group(1), re.M))


async def _grant(sessionmaker, code: str = "civil_defense", on: bool = True) -> None:
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


async def _person(sessionmaker, last_name: str = "Спасателев") -> str:
    """Человек из ЯДРА: формирование не заводит своих «бойцов»."""

    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        company = (
            (await session.execute(select(Company).where(Company.tenant_id == tenant.id)))
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
            last_name=last_name,
            first_name="Пётр",
            middle_name="Иванович",
        )
        session.add(person)
        await session.commit()
        return str(person.id)


async def _formation(
    async_client,
    headers,
    *,
    name: str = "Звено пожаротушения",
    kind: str = "nasf",
    commander_id: str | None = None,
) -> dict:
    payload: dict[str, object] = {"name": name, "kind": kind}
    if commander_id is not None:
        payload["commander_person_id"] = commander_id
    response = await async_client.post(f"{_API}/formations", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


class TestРеестрФормирований:
    async def test_без_выдачи_модуль_невидим(self, async_client, make_auth_headers) -> None:
        headers = await make_auth_headers()
        response = await async_client.get(f"{_API}/formations", headers=headers)
        assert response.status_code == 404

    async def test_формирование_заводится_с_видом_словами(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        created = await async_client.post(
            f"{_API}/formations",
            json={
                "name": "Звено пожаротушения",
                "kind": "nasf",
                "purpose": "Тушение возгораний до прибытия подразделений",
            },
            headers=headers,
        )
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["kind_label"] == "НАСФ (аварийно-спасательное формирование)"
        # Командир не назначен — это названо словами, а не пустой клеткой.
        assert body["commander_name"] is None
        assert body["members_active"] == 0

    async def test_неизвестный_вид_отвергается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        response = await async_client.post(
            f"{_API}/formations",
            json={"name": "Отряд", "kind": "дружина"},
            headers=headers,
        )
        assert response.status_code == 422, response.text

    async def test_дубль_названия_отвергается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        await _formation(async_client, headers, name="Пост РХН")
        response = await async_client.post(
            f"{_API}/formations",
            json={"name": "Пост РХН", "kind": "nfgo"},
            headers=headers,
        )
        assert response.status_code == 422, response.text

    async def test_командир_из_ядра_и_фио_в_ответе(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        commander_id = await _person(sessionmaker, "Командиров")
        body = await _formation(
            async_client, headers, name="Санитарный пост", commander_id=commander_id
        )
        assert body["commander_name"] == "Командиров Пётр Иванович"

    async def test_несуществующий_командир_отвергается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        response = await async_client.post(
            f"{_API}/formations",
            json={
                "name": "Отряд",
                "kind": "nasf",
                "commander_person_id": "00000000-0000-0000-0000-000000000000",
            },
            headers=headers,
        )
        assert response.status_code == 404, response.text


class TestСоставФормирования:
    async def test_человек_из_ядра_включается_в_состав(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        formation = await _formation(async_client, headers, name="Звено связи")
        person_id = await _person(sessionmaker, "Связистов")
        added = await async_client.post(
            f"{_API}/formations/{formation['id']}/members",
            json={
                "person_id": person_id,
                "role_in_formation": "Связной",
                "assigned_on": str(date.today() - timedelta(days=30)),
            },
            headers=headers,
        )
        assert added.status_code == 201, added.text
        body = added.json()
        assert body["person_name"] == "Связистов Пётр Иванович"
        assert body["released_on"] is None

    async def test_несуществующий_человек_отвергается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        formation = await _formation(async_client, headers, name="Звено охраны")
        response = await async_client.post(
            f"{_API}/formations/{formation['id']}/members",
            json={"person_id": "00000000-0000-0000-0000-000000000000"},
            headers=headers,
        )
        assert response.status_code == 404, response.text

    async def test_дубль_человека_в_составе_отвергается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        formation = await _formation(async_client, headers, name="Звено разведки")
        person_id = await _person(sessionmaker, "Разведчиков")
        first = await async_client.post(
            f"{_API}/formations/{formation['id']}/members",
            json={"person_id": person_id},
            headers=headers,
        )
        assert first.status_code == 201, first.text
        second = await async_client.post(
            f"{_API}/formations/{formation['id']}/members",
            json={"person_id": person_id},
            headers=headers,
        )
        assert second.status_code == 422, second.text

    async def test_тот_же_человек_в_другом_формировании_принимается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Совместительство в формированиях — обычная практика малых организаций."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        first = await _formation(async_client, headers, name="Звено оповещения")
        second = await _formation(async_client, headers, name="Эвакуационная группа", kind="nfgo")
        person_id = await _person(sessionmaker, "Совместителев")
        for formation in (first, second):
            response = await async_client.post(
                f"{_API}/formations/{formation['id']}/members",
                json={"person_id": person_id},
                headers=headers,
            )
            assert response.status_code == 201, response.text

    async def test_вывод_из_состава_это_дата_а_не_удаление(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Отчисленный остаётся в истории формирования."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        formation = await _formation(async_client, headers, name="Пост наблюдения")
        person_id = await _person(sessionmaker, "Выбывалов")
        added = await async_client.post(
            f"{_API}/formations/{formation['id']}/members",
            json={"person_id": person_id},
            headers=headers,
        )
        member_id = added.json()["id"]
        # Дата берётся ОДИН раз: сравнивать ответ с `date.today()`, посчитанным
        # заново, значит ломаться, если прогон пересёк полночь.
        released_on = date.today()
        released = await async_client.patch(
            f"{_API}/formations/{formation['id']}/members/{member_id}",
            json={"released_on": str(released_on)},
            headers=headers,
        )
        assert released.status_code == 200, released.text
        listed = await async_client.get(
            f"{_API}/formations/{formation['id']}/members", headers=headers
        )
        items = listed.json()["items"]
        # Строка не исчезла — история цела, но статус назван словами.
        assert len(items) == 1
        assert items[0]["released_on"] == str(released_on)
        assert items[0]["status_label"] == "Выведен из состава"

    async def test_повторное_включение_сбрасывает_дату_вывода(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        formation = await _formation(async_client, headers, name="Звено подвоза")
        person_id = await _person(sessionmaker, "Возвращенцев")
        added = await async_client.post(
            f"{_API}/formations/{formation['id']}/members",
            json={"person_id": person_id},
            headers=headers,
        )
        member_id = added.json()["id"]
        await async_client.patch(
            f"{_API}/formations/{formation['id']}/members/{member_id}",
            json={"released_on": str(date.today() - timedelta(days=10))},
            headers=headers,
        )
        again = await async_client.post(
            f"{_API}/formations/{formation['id']}/members",
            json={"person_id": person_id},
            headers=headers,
        )
        # Не дубль, а возвращение: та же строка, дата вывода снята.
        assert again.status_code == 200, again.text
        assert again.json()["id"] == member_id
        assert again.json()["released_on"] is None


class TestСводкаИГраница:
    async def test_сводка_считает_виды_командиров_и_численность(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        commander_id = await _person(sessionmaker, "Начальников")
        with_commander = await _formation(
            async_client,
            headers,
            name="Звено пожаротушения",
            commander_id=commander_id,
        )
        await _formation(async_client, headers, name="Эвакуационная группа", kind="nfgo")
        member_id = await _person(sessionmaker, "Членов")
        former_id = await _person(sessionmaker, "Бывший")
        for pid in (member_id, former_id):
            await async_client.post(
                f"{_API}/formations/{with_commander['id']}/members",
                json={"person_id": pid},
                headers=headers,
            )
        listed = await async_client.get(
            f"{_API}/formations/{with_commander['id']}/members", headers=headers
        )
        former_row = next(
            row for row in listed.json()["items"] if row["person_name"].startswith("Бывший")
        )
        await async_client.patch(
            f"{_API}/formations/{with_commander['id']}/members/{former_row['id']}",
            json={"released_on": str(date.today())},
            headers=headers,
        )

        readiness = await async_client.get(f"{_API}/readiness", headers=headers)
        assert readiness.status_code == 200, readiness.text
        body = readiness.json()
        assert body["total_formations"] == 2
        assert body["by_kind"] == {"nasf": 1, "nfgo": 1}
        assert body["without_commander"] == 1
        # Выведенный из состава в численность не входит.
        assert body["members_active"] == 1

    async def test_платформа_не_решает_сколько_формирований_нужно(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """ГРАНИЦА: обязанность создавать формирования следует из категории
        организации по ГО и решений органа управления ГОЧС — не из платформы."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        body = await _formation(async_client, headers, name="Звено ГО")
        forbidden = {
            "formations_required",
            "required_count",
            "understaffed",
            "staffing_norm",
        }
        assert forbidden.isdisjoint(body.keys())
        readiness = await async_client.get(f"{_API}/readiness", headers=headers)
        assert forbidden.isdisjoint(readiness.json().keys())

    async def test_чужое_формирование_не_читается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        response = await async_client.patch(
            f"{_API}/formations/00000000-0000-0000-0000-000000000000",
            json={"name": "Чужое"},
            headers=headers,
        )
        assert response.status_code == 404, response.text


class TestСловарьВидовФормированийНаФронте:
    """Срез-109: вид формирования выбирают в форме из копии словаря.

    НАСФ и НФГО — разные формирования с разными задачами; подписи должны
    совпадать с ядром, иначе человек заведёт не то, что имел в виду.
    """

    def test_виды_формирований_на_фронте_совпадают_с_бэкендом(self) -> None:
        front = _front_map("CD_FORMATION_KIND_TITLES")
        assert front == CD_FORMATION_KINDS, sorted(front.items() ^ CD_FORMATION_KINDS.items())
