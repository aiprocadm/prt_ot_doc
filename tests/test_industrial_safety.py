"""Контур ПромБез срез-1 (Доп. №1 разд. 54.2): реестр ОПО.

СВЕРКА, С КОТОРОЙ НАЧАЛСЯ СРЕЗ. Раздел 54.2 требует «реестр ОПО:
идентификация, класс опасности, регистрационные сведения». В продукте не было
ни реестра, ни сущности — только три поля у ПЛОЩАДКИ:

* ``Site.is_hazardous_production_facility`` — булев признак,
* ``Site.opo_register_number`` — номер строкой,
* ``Site.hazard_class`` — **свободная строка на 32 символа**.

И последнее поле перегружено ДВУМЯ РАЗНЫМИ СМЫСЛАМИ: в него кладут и класс
опасности ОПО («II»), и категорию пожарной опасности помещения («В2») — это
видно прямо в фикстурах экранов. Значит вопрос «сколько у нас объектов I
класса» не имел ответа по построению, а «идентификация и класс опасности» из
ТЗ были невыполнимы — та же форма дыры, что у свободной строки вида
инструктажа (контур ПБ, срез-3).

Плюс площадка и ОПО — не одно и то же: на одной площадке бывает несколько
зарегистрированных объектов (котельная, склад ГСМ, кран), у каждого свой
регистрационный номер и свой класс опасности. Полями площадки этого не
выразить в принципе.

Границы среза названы прямо: класс опасности — ЗАКРЫТЫЙ словарь I–IV
(ФЗ-116), а вот ``Site.hazard_class`` НЕ трогается — там лежат живые данные
двух разных смыслов, и их разбор это отдельное решение, а не побочный эффект
этого среза.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from sqlalchemy import select

from app.models.feature import Feature, FeatureEnablement
from app.models.industrial_safety import OPO_HAZARD_CLASSES, OPO_STATUSES
from app.models.models import Tenant

pytestmark = pytest.mark.anyio

_API = "/api/v1/industrial-safety"


_FRONTEND_OPO_API = (
    Path(__file__).resolve().parents[1]
    / "frontend"
    / "src"
    / "api"
    / "industrialSafety.ts"
)


def _front_map(name: str) -> dict[str, str]:
    """Читает map подписей из ``frontend/src/api/industrialSafety.ts``."""

    text = _FRONTEND_OPO_API.read_text(encoding="utf-8")
    block = re.search(rf"{name}:\s*Record<[^>]+>\s*=\s*\{{(.*?)\n\}}", text, re.S)
    assert block is not None, f"не нашёлся map {name}"
    return dict(re.findall(r'^\s*([A-Za-z_]+):\s*"([^"]+)"', block.group(1), re.M))


async def _grant(sessionmaker, code: str = "industrial_safety", on: bool = True) -> None:
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
            session.add(FeatureEnablement(tenant_id=tenant.id, feature_id=feature.id, on=on))
        else:
            grant.on = on
        await session.commit()


class TestРеестрОПО:
    async def test_без_выдачи_модуль_невидим(self, async_client, make_auth_headers) -> None:
        """Гейт роутерный — новая дисциплина защищена по построению (разд. 61.3)."""

        headers = await make_auth_headers()
        response = await async_client.get(f"{_API}/facilities", headers=headers)
        assert response.status_code == 404

    async def test_объект_заводится_с_классом_словами(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        created = await async_client.post(
            f"{_API}/facilities",
            json={
                "name": "Сеть газопотребления котельной",
                "register_number": "А01-12345-0001",
                "hazard_class": "III",
                "registered_on": "2021-06-15",
                "responsible": "Главный инженер Петров",
            },
            headers=headers,
        )
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["hazard_class"] == "III"
        assert body["hazard_class_label"].startswith("III класс")
        assert body["status"] == "registered"

    async def test_класс_опасности_закрытый_словарь(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Дыра площадки не повторяется: класс — I–IV, а не что угодно.

        Свободная строка снова сделала бы вопрос «сколько объектов I класса»
        неотвечаемым: «I», «1», «первый», «В2» были бы четырьмя разными
        классами.
        """

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        response = await async_client.post(
            f"{_API}/facilities",
            json={
                "name": "Склад",
                "register_number": "А01-00001-0002",
                "hazard_class": "В2",
            },
            headers=headers,
        )
        assert response.status_code == 422
        assert "Неизвестный класс опасности" in response.text

    async def test_все_четыре_класса_принимаются(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        for index, hazard_class in enumerate(("I", "II", "III", "IV")):
            response = await async_client.post(
                f"{_API}/facilities",
                json={
                    "name": f"Объект {hazard_class}",
                    "register_number": f"А01-00002-000{index}",
                    "hazard_class": hazard_class,
                },
                headers=headers,
            )
            assert response.status_code == 201, f"{hazard_class}: {response.text}"

    async def test_регистрационный_номер_обязателен(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """ОПО без номера в госреестре не существует — это его удостоверение."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        response = await async_client.post(
            f"{_API}/facilities",
            json={"name": "Объект без номера", "hazard_class": "IV"},
            headers=headers,
        )
        assert response.status_code == 422

    async def test_номер_не_дублируется_внутри_арендатора(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Два объекта с одним госномером — это один объект, заведённый дважды."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        payload = {
            "name": "Котельная",
            "register_number": "А01-77777-0001",
            "hazard_class": "III",
        }
        first = await async_client.post(f"{_API}/facilities", json=payload, headers=headers)
        assert first.status_code == 201, first.text
        second = await async_client.post(
            f"{_API}/facilities",
            json={**payload, "name": "Та же котельная"},
            headers=headers,
        )
        assert second.status_code == 422
        assert "уже заведён" in second.text

    async def test_несколько_опо_на_одной_площадке(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Ради этого реестр и заводился: полями площадки такое не выразить.

        На одной площадке бывает несколько зарегистрированных объектов, у
        каждого свой номер и свой класс опасности.
        """

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        for suffix, hazard_class in (("0001", "II"), ("0002", "IV")):
            response = await async_client.post(
                f"{_API}/facilities",
                json={
                    "name": f"Объект {suffix}",
                    "register_number": f"А01-55555-{suffix}",
                    "hazard_class": hazard_class,
                },
                headers=headers,
            )
            assert response.status_code == 201, response.text

        listed = await async_client.get(f"{_API}/facilities", headers=headers)
        assert listed.status_code == 200
        assert listed.json()["total"] >= 2

    async def test_исключение_из_реестра_не_удаляет_объект(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Объект исключают из госреестра — история эксплуатации остаётся."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        created = await async_client.post(
            f"{_API}/facilities",
            json={
                "name": "Выведенный из эксплуатации участок",
                "register_number": "А01-88888-0001",
                "hazard_class": "IV",
            },
            headers=headers,
        )
        patched = await async_client.patch(
            f"{_API}/facilities/{created.json()['id']}",
            json={"status": "excluded", "excluded_on": "2026-03-01"},
            headers=headers,
        )
        assert patched.status_code == 200, patched.text
        assert patched.json()["status"] == "excluded"
        assert patched.json()["status_label"] == "Исключён из реестра"

    async def test_неизвестное_состояние_отвергается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        created = await async_client.post(
            f"{_API}/facilities",
            json={
                "name": "Объект",
                "register_number": "А01-99999-0001",
                "hazard_class": "I",
            },
            headers=headers,
        )
        response = await async_client.patch(
            f"{_API}/facilities/{created.json()['id']}",
            json={"status": "заморожен"},
            headers=headers,
        )
        assert response.status_code == 422
        assert "Неизвестное состояние" in response.text


class TestСводкаПромБеза:
    async def test_сводка_считает_объекты_по_классам(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """«Класс опасности» из ТЗ — величина, по которой надзор и планирует.

        Объекты I и II класса — это постоянный госнадзор и обязательная
        декларация промышленной безопасности, поэтому их число видно отдельно.
        """

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        before = (await async_client.get(f"{_API}/readiness", headers=headers)).json()

        await async_client.post(
            f"{_API}/facilities",
            json={
                "name": "Опасный объект",
                "register_number": "А01-11111-0001",
                "hazard_class": "I",
            },
            headers=headers,
        )
        after = (await async_client.get(f"{_API}/readiness", headers=headers)).json()
        assert after["total_facilities"] == before["total_facilities"] + 1
        assert after["by_class"]["I"] == before["by_class"]["I"] + 1

    async def test_исключённые_в_действующие_не_попадают(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        created = await async_client.post(
            f"{_API}/facilities",
            json={
                "name": "Объект под исключение",
                "register_number": "А01-22222-0001",
                "hazard_class": "II",
            },
            headers=headers,
        )
        before = (await async_client.get(f"{_API}/readiness", headers=headers)).json()
        await async_client.patch(
            f"{_API}/facilities/{created.json()['id']}",
            json={"status": "excluded"},
            headers=headers,
        )
        after = (await async_client.get(f"{_API}/readiness", headers=headers)).json()
        assert after["total_facilities"] == before["total_facilities"] - 1
        assert after["by_class"]["II"] == before["by_class"]["II"] - 1


class TestИзоляцияАрендатора:
    async def test_чужая_площадка_не_подтверждается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        response = await async_client.post(
            f"{_API}/facilities",
            json={
                "name": "Объект",
                "register_number": "А01-33333-0001",
                "hazard_class": "III",
                "site_id": "no-such-site",
            },
            headers=headers,
        )
        assert response.status_code == 422
        assert "Площадка не найдена" in response.text

    async def test_чужой_объект_не_правится(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        response = await async_client.patch(
            f"{_API}/facilities/does-not-exist",
            json={"name": "Подмена"},
            headers=headers,
        )
        assert response.status_code == 404


class TestСловариОпоНаФронте:
    """Срез-105: класс и состояние ОПО выбирают в форме из копий словарей.

    Список формы строится из ``OPO_HAZARD_CLASS_TITLES`` / ``OPO_STATUS_TITLES``
    в ``api/industrialSafety.ts``: значение, добавленное только на бэкенде,
    нельзя было бы ни выбрать, ни прочитать словами.
    """

    def test_классы_опасности_на_фронте_совпадают_с_бэкендом(self) -> None:
        front = _front_map("OPO_HAZARD_CLASS_TITLES")
        assert front == OPO_HAZARD_CLASSES, sorted(
            front.items() ^ OPO_HAZARD_CLASSES.items()
        )

    def test_состояния_объекта_на_фронте_совпадают_с_бэкендом(self) -> None:
        front = _front_map("OPO_STATUS_TITLES")
        assert front == OPO_STATUSES, sorted(front.items() ^ OPO_STATUSES.items())

