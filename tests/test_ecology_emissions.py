"""Контур экологии срез-3 (Доп. №1 разд. 55.2): выбросы — источники и нормативы.

Требование: «Выбросы: инвентаризация, нормативы, производственный экологический
контроль (ПЭК), план-график замеров». Этот срез закрывает первые две части —
инвентаризацию стационарных источников и нормативы по веществам; ПЭК и
план-график замеров идут следующим срезом (замер опирается на источник и
норматив, которых до сих пор не существовало).

СВЕРКА. Ни источников, ни нормативов в продукте не было: по разделу 55 есть
только объекты НВОС (срез-1) и отходы (срез-2).

Решения:

* **источник принадлежит объекту НВОС**, а не площадке: инвентаризация и
  разрешения оформляются по зарегистрированному объекту, и на одной площадке
  объектов бывает несколько (это закрыл срез-1);
* **номер источника уникален в пределах объекта**, а не арендатора: нумерация
  источников ведётся по объекту, и «источник №1» есть у каждого;
* **норматив — на пару «источник + вещество»**: ПДВ устанавливается по каждому
  загрязняющему веществу отдельно, одним числом на источник его не выразить.

ГРАНИЦА: платформа НЕ РАССЧИТЫВАЕТ норматив. ПДВ устанавливается расчётом
рассеивания в проекте нормативов и утверждается разрешением; исходных данных
(параметры выброса, метеоусловия, фоновые концентрации) в системе нет. Храним
внесённое — тот же довод, что у категории объекта и лимита отходов.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select

from app.models.ecology import EMISSION_SOURCE_KINDS
from app.models.feature import Feature, FeatureEnablement
from app.models.models import Tenant

pytestmark = pytest.mark.anyio

_API = "/api/v1/ecology"
_FRONTEND_ECOLOGY_API = (
    Path(__file__).resolve().parents[1] / "frontend" / "src" / "api" / "ecology.ts"
)


async def _grant(sessionmaker, code: str = "ecology", on: bool = True) -> None:
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


async def _facility(async_client, headers, suffix: str = "0001") -> str:
    response = await async_client.post(
        f"{_API}/facilities",
        json={
            "name": f"Площадка {suffix}",
            "register_number": f"12-0177-01{suffix}-П",
            "category": "II",
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _source(async_client, headers, facility_id: str, number: str = "0001") -> str:
    response = await async_client.post(
        f"{_API}/emission-sources",
        json={
            "facility_id": facility_id,
            "source_number": number,
            "name": "Труба котельной",
            "kind": "organized",
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


class TestИнвентаризацияИсточников:
    async def test_без_выдачи_модуль_невидим(self, async_client, make_auth_headers) -> None:
        headers = await make_auth_headers()
        response = await async_client.get(f"{_API}/emission-sources", headers=headers)
        assert response.status_code == 404

    async def test_источник_заводится_с_типом_словами(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        facility_id = await _facility(async_client, headers)
        created = await async_client.post(
            f"{_API}/emission-sources",
            json={
                "facility_id": facility_id,
                "source_number": "0001",
                "name": "Труба котельной",
                "kind": "organized",
                "location": "Котельная, ось А",
                "inventoried_on": str(date.today() - timedelta(days=200)),
            },
            headers=headers,
        )
        assert created.status_code == 201, created.text
        assert created.json()["kind_label"] == "Организованный источник"

    async def test_неизвестный_тип_отвергается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        facility_id = await _facility(async_client, headers, "0002")
        response = await async_client.post(
            f"{_API}/emission-sources",
            json={
                "facility_id": facility_id,
                "source_number": "0002",
                "name": "Что-то",
                "kind": "труба",
            },
            headers=headers,
        )
        assert response.status_code == 422
        assert "Неизвестный тип источника" in response.text

    async def test_источник_без_объекта_не_принимается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Инвентаризация и разрешения оформляются по объекту НВОС."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        response = await async_client.post(
            f"{_API}/emission-sources",
            json={
                "facility_id": "no-such-facility",
                "source_number": "0003",
                "name": "Труба",
                "kind": "organized",
            },
            headers=headers,
        )
        assert response.status_code == 422
        assert "Объект НВОС не найден" in response.text

    async def test_номер_уникален_в_пределах_объекта(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Нумерация источников ведётся ПО ОБЪЕКТУ: «источник №1» есть у каждого.

        Поэтому дубль запрещён внутри объекта, но тот же номер на другом
        объекте — норма, а не ошибка.
        """

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        first_facility = await _facility(async_client, headers, "0004")
        second_facility = await _facility(async_client, headers, "0005")

        await _source(async_client, headers, first_facility, "0001")
        duplicate = await async_client.post(
            f"{_API}/emission-sources",
            json={
                "facility_id": first_facility,
                "source_number": "0001",
                "name": "Вторая труба",
                "kind": "organized",
            },
            headers=headers,
        )
        assert duplicate.status_code == 422
        assert "уже заведён" in duplicate.text

        same_number_other_facility = await async_client.post(
            f"{_API}/emission-sources",
            json={
                "facility_id": second_facility,
                "source_number": "0001",
                "name": "Труба другого объекта",
                "kind": "organized",
            },
            headers=headers,
        )
        assert same_number_other_facility.status_code == 201, same_number_other_facility.text


class TestНормативыПДВ:
    async def test_норматив_заводится_по_веществу(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """ПДВ устанавливается по КАЖДОМУ веществу отдельно."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        facility_id = await _facility(async_client, headers, "0006")
        source_id = await _source(async_client, headers, facility_id)
        today = date.today()

        created = await async_client.post(
            f"{_API}/emission-norms",
            json={
                "source_id": source_id,
                "substance": "Азота диоксид",
                "limit_grams_per_second": "0.0250",
                "limit_tons_per_year": "0.780",
                "permit_number": "РВ-77-000123",
                "valid_until": str(today + timedelta(days=900)),
            },
            headers=headers,
        )
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["substance"] == "Азота диоксид"
        assert body["validity_status"] == "ok"
        assert body["validity_status_label"] == "Действует"

    async def test_два_норматива_на_одно_вещество_не_заводятся(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        facility_id = await _facility(async_client, headers, "0007")
        source_id = await _source(async_client, headers, facility_id)
        payload = {
            "source_id": source_id,
            "substance": "Углерода оксид",
            "limit_tons_per_year": "1.200",
        }
        first = await async_client.post(f"{_API}/emission-norms", json=payload, headers=headers)
        assert first.status_code == 201, first.text
        second = await async_client.post(f"{_API}/emission-norms", json=payload, headers=headers)
        assert second.status_code == 422
        assert "уже задан" in second.text

    async def test_норматив_без_значений_не_принимается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Норматив без единого значения ничего не нормирует."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        facility_id = await _facility(async_client, headers, "0008")
        source_id = await _source(async_client, headers, facility_id)
        response = await async_client.post(
            f"{_API}/emission-norms",
            json={"source_id": source_id, "substance": "Пыль неорганическая"},
            headers=headers,
        )
        assert response.status_code == 422
        assert "хотя бы одно значение" in response.text

    async def test_просроченное_разрешение_названо_просроченным(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        facility_id = await _facility(async_client, headers, "0009")
        source_id = await _source(async_client, headers, facility_id)
        created = await async_client.post(
            f"{_API}/emission-norms",
            json={
                "source_id": source_id,
                "substance": "Серы диоксид",
                "limit_tons_per_year": "0.500",
                "valid_until": str(date.today() - timedelta(days=1)),
            },
            headers=headers,
        )
        assert created.json()["validity_status"] == "overdue"
        assert created.json()["validity_status_label"] == "Разрешение просрочено"

    async def test_бессрочный_норматив_просрочкой_не_считается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Для объектов III категории нормативы могут действовать бессрочно.

        Пустой срок — это «бессрочно», а не «просрочено»: тот же выбор, что у
        срока пересмотра документов ПБ.
        """

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        facility_id = await _facility(async_client, headers, "0010")
        source_id = await _source(async_client, headers, facility_id)
        created = await async_client.post(
            f"{_API}/emission-norms",
            json={
                "source_id": source_id,
                "substance": "Метан",
                "limit_tons_per_year": "3.000",
            },
            headers=headers,
        )
        assert created.json()["validity_status"] == "ok"
        assert created.json()["valid_until"] is None


class TestСводкаВыбросов:
    async def test_счётчики_выбросов_в_сводке(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        before = (await async_client.get(f"{_API}/readiness", headers=headers)).json()

        facility_id = await _facility(async_client, headers, "0011")
        source_id = await _source(async_client, headers, facility_id)
        await async_client.post(
            f"{_API}/emission-norms",
            json={
                "source_id": source_id,
                "substance": "Азота оксид",
                "limit_tons_per_year": "0.100",
                "valid_until": str(date.today() - timedelta(days=2)),
            },
            headers=headers,
        )

        after = (await async_client.get(f"{_API}/readiness", headers=headers)).json()
        assert after["emission_sources"] == before["emission_sources"] + 1
        assert after["emission_norms"] == before["emission_norms"] + 1
        assert after["emission_permits_overdue"] == before["emission_permits_overdue"] + 1

    async def test_источники_без_нормативов_названы_числом(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Источник в инвентаризации без единого норматива — это факт, а не
        нарушение: нормативы устанавливаются не на все вещества и не сразу."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        before = (await async_client.get(f"{_API}/readiness", headers=headers)).json()
        facility_id = await _facility(async_client, headers, "0012")
        await _source(async_client, headers, facility_id)
        after = (await async_client.get(f"{_API}/readiness", headers=headers)).json()
        assert (
            after["emission_sources_without_norms"] == before["emission_sources_without_norms"] + 1
        )

    async def test_норматив_не_рассчитывается_платформой(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """ГРАНИЦА: ПДВ устанавливается расчётом рассеивания в проекте
        нормативов и утверждается разрешением.

        Исходных данных (параметры выброса, метеоусловия, фоновые
        концентрации) в системе нет. Сторож против соблазна «предложить ПДВ» в
        следующей волне.
        """

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        body = (await async_client.get(f"{_API}/readiness", headers=headers)).json()
        assert "suggested_limit" not in body
        assert "limit_exceeded" not in body


class TestИзоляцияАрендатора:
    async def test_чужой_источник_не_правится(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        response = await async_client.patch(
            f"{_API}/emission-sources/does-not-exist",
            json={"name": "Подмена"},
            headers=headers,
        )
        assert response.status_code == 404

    async def test_чужой_норматив_не_правится(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        response = await async_client.patch(
            f"{_API}/emission-norms/does-not-exist",
            json={"substance": "Подмена"},
            headers=headers,
        )
        assert response.status_code == 404


class TestСловарьВидовИсточниковНаФронте:
    """Срез-100: вид источника выбирают в форме из копии словаря на фронте.

    Список формы строится из ``EMISSION_SOURCE_KIND_TITLES`` в
    ``api/ecology.ts``: значение, добавленное только на бэкенде, нельзя было бы
    ни выбрать, ни прочитать словами.
    """

    def test_виды_источников_на_фронте_совпадают_с_бэкендом(self) -> None:
        text = _FRONTEND_ECOLOGY_API.read_text(encoding="utf-8")
        block = re.search(
            r"EMISSION_SOURCE_KIND_TITLES:\s*Record<string,\s*string>\s*=\s*\{(.*?)\}",
            text,
            re.S,
        )
        assert block is not None, "не нашёлся map EMISSION_SOURCE_KIND_TITLES"
        front = dict(re.findall(r'^\s*([A-Za-z_]+):\s*"([^"]+)"', block.group(1), re.M))
        assert front == EMISSION_SOURCE_KINDS, sorted(front.items() ^ EMISSION_SOURCE_KINDS.items())
