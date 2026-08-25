"""Контур экологии срез-1 (Доп. №1 разд. 55.1): объекты НВОС.

СВЕРКА, С КОТОРОЙ НАЧАЛСЯ СРЕЗ. Раздел 55.1 требует «объекты НВОС
(негативного воздействия на окружающую среду): категория объекта (I–IV),
постановка на учёт, актуализация сведений». В продукте по экологии не было
НИ ОДНОЙ сущности:

* поиск по моделям (``waste``, ``отход``, ``эколог``, ``НВОС``, ``выброс``,
  ``водопольз``) не даёт ничего;
* дисциплина ``Discipline.ECOLOGY`` объявлена, но числится в
  ``UNMEASURED_DISCIPLINES`` («поимённый учёт экологии не ведётся»), в
  источниках календаря её нет, правил библиотеки нет — и сама библиотека это
  фиксирует причиной: «в системе нет ни одного события экологии: объектов
  НВОС, отходов и отчётности по ПЭК в продукте пока нет»;
* есть только комплект документов ``ECO_WASTE`` (реестр, договор, памятка),
  где ВСЕ значения вводятся руками и никуда не сохраняются;
* модуля ``ecology`` в каталоге подписки нет — дисциплину нельзя ни продать,
  ни выключить (реестр модулей прямо объясняет: «у них нет ни экранов, ни
  сущностей, и модуль без функциональности — это продажа пустоты»).

Этот срез даёт дисциплине содержание: реестр объектов НВОС с ЗАКРЫТОЙ
категорией I–IV, номером в государственном реестре и датой актуализации
сведений — и вместе с ним модуль, который можно продать и выключить.

ГРАНИЦА: категорию объекта платформа НЕ ВЫЧИСЛЯЕТ. Она присваивается при
постановке на государственный учёт по критериям постановления Правительства, и
исходных данных для такого вывода (мощность, виды воздействия, применяемые
технологии) в системе нет. Храним внесённое специалистом — тот же довод, что у
интервала тренировок и требования ЭПБ.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.models.feature import Feature, FeatureEnablement
from app.models.models import Tenant

pytestmark = pytest.mark.anyio

_API = "/api/v1/ecology"


async def _grant(sessionmaker, code: str = "ecology", on: bool = True) -> None:
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


class TestРеестрНВОС:
    async def test_без_выдачи_модуль_невидим(self, async_client, make_auth_headers) -> None:
        """Гейт роутерный — новая дисциплина защищена по построению (разд. 61.3)."""

        headers = await make_auth_headers()
        response = await async_client.get(f"{_API}/facilities", headers=headers)
        assert response.status_code == 404

    async def test_объект_заводится_с_категорией_словами(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        today = date.today()
        created = await async_client.post(
            f"{_API}/facilities",
            json={
                "name": "Производственная площадка №1",
                "register_number": "12-0177-001234-П",
                "category": "II",
                "registered_on": str(today - timedelta(days=400)),
                "responsible": "Эколог Иванова",
            },
            headers=headers,
        )
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["category"] == "II"
        assert body["category_label"].startswith("II категория")
        assert body["status"] == "registered"

    async def test_категория_закрытый_словарь(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Категория — I–IV, а не что угодно.

        От категории зависит и режим надзора, и состав отчётности; свободная
        строка сделала бы вопрос «сколько у нас объектов I категории»
        неотвечаемым — ровно как это случилось с классом опасности площадки.
        """

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        response = await async_client.post(
            f"{_API}/facilities",
            json={
                "name": "Объект",
                "register_number": "12-0177-000001-П",
                "category": "V",
            },
            headers=headers,
        )
        assert response.status_code == 422
        assert "Неизвестная категория" in response.text

    async def test_все_четыре_категории_принимаются(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        for index, category in enumerate(("I", "II", "III", "IV")):
            response = await async_client.post(
                f"{_API}/facilities",
                json={
                    "name": f"Объект {category}",
                    "register_number": f"12-0177-00010{index}-П",
                    "category": category,
                },
                headers=headers,
            )
            assert response.status_code == 201, f"{category}: {response.text}"

    async def test_номер_в_реестре_обязателен(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Объект НВОС без номера в госреестре не существует как учтённый."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        response = await async_client.post(
            f"{_API}/facilities",
            json={"name": "Объект без номера", "category": "IV"},
            headers=headers,
        )
        assert response.status_code == 422

    async def test_номер_не_дублируется(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        payload = {
            "name": "Котельная",
            "register_number": "12-0177-005555-П",
            "category": "III",
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

    async def test_актуализация_сведений_учитывается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """«Актуализация сведений» из ТЗ — это дата, а не галочка.

        Сведения об объекте актуализируют при изменении характеристик, и
        специалисту важно видеть, когда это делали в последний раз.
        """

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        today = date.today()
        created = await async_client.post(
            f"{_API}/facilities",
            json={
                "name": "Площадка №2",
                "register_number": "12-0177-006666-П",
                "category": "II",
            },
            headers=headers,
        )
        assert created.json()["actualized_on"] is None

        patched = await async_client.patch(
            f"{_API}/facilities/{created.json()['id']}",
            json={"actualized_on": str(today)},
            headers=headers,
        )
        assert patched.status_code == 200, patched.text
        assert patched.json()["actualized_on"] == str(today)

    async def test_снятие_с_учёта_не_удаляет_объект(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        created = await async_client.post(
            f"{_API}/facilities",
            json={
                "name": "Выведенная площадка",
                "register_number": "12-0177-007777-П",
                "category": "IV",
            },
            headers=headers,
        )
        patched = await async_client.patch(
            f"{_API}/facilities/{created.json()['id']}",
            json={"status": "excluded", "excluded_on": str(date.today())},
            headers=headers,
        )
        assert patched.status_code == 200, patched.text
        assert patched.json()["status_label"] == "Снят с учёта"


class TestСводкаЭкологии:
    async def test_разрез_по_категориям(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """От категории зависят и надзор, и состав отчётности."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        before = (await async_client.get(f"{_API}/readiness", headers=headers)).json()

        await async_client.post(
            f"{_API}/facilities",
            json={
                "name": "Объект I категории",
                "register_number": "12-0177-008888-П",
                "category": "I",
            },
            headers=headers,
        )
        after = (await async_client.get(f"{_API}/readiness", headers=headers)).json()
        assert after["total_facilities"] == before["total_facilities"] + 1
        assert after["by_category"]["I"] == before["by_category"]["I"] + 1

    async def test_снятые_с_учёта_не_считаются_действующими(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        created = await async_client.post(
            f"{_API}/facilities",
            json={
                "name": "Под снятие",
                "register_number": "12-0177-009999-П",
                "category": "III",
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
        assert after["excluded_facilities"] == before["excluded_facilities"] + 1

    async def test_категория_не_вычисляется_платформой(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """ГРАНИЦА: категорию присваивают при постановке на учёт, а не мы.

        Она определяется по критериям постановления Правительства (мощность,
        виды воздействия, технологии), а этих данных в системе нет. Сторож
        против соблазна «вычислить категорию» в следующей волне: в ответе нет
        ни предлагаемой категории, ни признака несоответствия.
        """

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        body = (await async_client.get(f"{_API}/readiness", headers=headers)).json()
        assert "suggested_category" not in body
        assert "category_mismatch" not in body


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
                "register_number": "12-0177-001111-П",
                "category": "III",
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
