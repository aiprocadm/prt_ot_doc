"""Контур экологии срез-4 (Доп. №1 разд. 55.2): ПЭК и план-график замеров.

Требование: «Выбросы: инвентаризация, нормативы, производственный экологический
контроль (ПЭК), план-график замеров». Срез-3 закрыл инвентаризацию и нормативы;
этот срез закрывает оставшиеся две части — план-график замеров и сам ПЭК.

СВЕРКА. Ни плана-графика, ни замеров в продукте не было: слово «замер» по
контуру экологии не встречалось нигде, кроме обещания в комментарии среза-3.
Из-за этого превышение норматива до сих пор было НЕИЗМЕРИМО: норматив внесён,
а сравнивать его не с чем.

Решения:

* **строка плана — на пару «источник + вещество»**, ровно как норматив: замеряют
  конкретное вещество на конкретном источнике, «замер источника вообще» не
  бывает;
* **периодичность в месяцах** (как у медосмотров и СОУТ в этом же продукте), а
  не свой словарь «квартал/полугодие»: программы ПЭК задают и нетиповые сроки;
* **превышение — это ФАКТ сравнения двух внесённых чисел**: замер сравнивается
  с разовым нормативом (г/с) по той же паре. Нет норматива — «норматив не
  внесён», а НЕ «превышение»: молчание о нормативе нельзя выдавать за нарушение;
* **внесение замера двигает плановую дату вперёд по календарной сетке** —
  иначе строка плана навсегда остаётся просроченной (сборка данных умеет
  заводить, но не умеет исправлять уже заведённое).

ГРАНИЦА: платформа НЕ НАЗНАЧАЕТ периодичность замеров. Она берётся из
утверждённой программы ПЭК, которая зависит от категории объекта, перечня
веществ и решения надзорного органа. Поля «требуемая периодичность» в ответе
нет — есть только внесённая.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select

from app.models.ecology import PERIODICITY_LABELS
from app.models.feature import Feature, FeatureEnablement
from app.models.models import Tenant

pytestmark = pytest.mark.anyio

_API = "/api/v1/ecology"
_FRONTEND_ECOLOGY_API = (
    Path(__file__).resolve().parents[1] / "frontend" / "src" / "api" / "ecology.ts"
)


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
            session.add(
                FeatureEnablement(tenant_id=tenant.id, feature_id=feature.id, on=on)
            )
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


async def _norm(
    async_client,
    headers,
    source_id: str,
    substance: str = "Азота диоксид",
    grams: str | None = "0.025000",
    tons: str | None = None,
) -> str:
    payload: dict[str, object] = {"source_id": source_id, "substance": substance}
    if grams is not None:
        payload["limit_grams_per_second"] = grams
    if tons is not None:
        payload["limit_tons_per_year"] = tons
    response = await async_client.post(
        f"{_API}/emission-norms", json=payload, headers=headers
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _plan_item(
    async_client,
    headers,
    source_id: str,
    *,
    substance: str = "Азота диоксид",
    months: int = 3,
    next_due_on: date | None = None,
) -> str:
    response = await async_client.post(
        f"{_API}/monitoring-plan",
        json={
            "source_id": source_id,
            "substance": substance,
            "periodicity_months": months,
            "next_due_on": str(next_due_on or (date.today() + timedelta(days=60))),
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _setup(async_client, headers, sessionmaker, suffix: str = "0001") -> str:
    """Общая подготовка: модуль выдан, объект и источник заведены."""

    await _grant(sessionmaker)
    facility_id = await _facility(async_client, headers, suffix)
    return await _source(async_client, headers, facility_id, suffix)


class TestПланГрафикЗамеров:
    async def test_без_выдачи_модуль_невидим(
        self, async_client, make_auth_headers
    ) -> None:
        headers = await make_auth_headers()
        response = await async_client.get(f"{_API}/monitoring-plan", headers=headers)
        assert response.status_code == 404

    async def test_строка_плана_заводится_и_периодичность_названа_словами(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        source_id = await _setup(async_client, headers, sessionmaker)
        created = await async_client.post(
            f"{_API}/monitoring-plan",
            json={
                "source_id": source_id,
                "substance": "Азота диоксид",
                "periodicity_months": 3,
                "next_due_on": str(date.today() + timedelta(days=45)),
                "method": "ПНД Ф 13.1:2:3.25-99",
                "laboratory": "ИЛЦ «Эковоздух»",
            },
            headers=headers,
        )
        assert created.status_code == 201, created.text
        body = created.json()
        # Периодичность читается словами, а не числом «3».
        assert body["periodicity_label"] == "раз в квартал"
        assert body["status"] == "ok"
        assert body["last_measured_on"] is None

    async def test_нетиповая_периодичность_читается_числом_месяцев(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        source_id = await _setup(async_client, headers, sessionmaker, "0002")
        created = await async_client.post(
            f"{_API}/monitoring-plan",
            json={
                "source_id": source_id,
                "substance": "Углерода оксид",
                "periodicity_months": 4,
                "next_due_on": str(date.today() + timedelta(days=45)),
            },
            headers=headers,
        )
        assert created.status_code == 201, created.text
        assert created.json()["periodicity_label"] == "раз в 4 месяца"

    async def test_периодичность_вне_границ_отвергается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        source_id = await _setup(async_client, headers, sessionmaker, "0003")
        for months in (0, 61):
            response = await async_client.post(
                f"{_API}/monitoring-plan",
                json={
                    "source_id": source_id,
                    "substance": "Азота диоксид",
                    "periodicity_months": months,
                    "next_due_on": str(date.today()),
                },
                headers=headers,
            )
            assert response.status_code == 422, response.text

    async def test_дубль_пары_источник_вещество_отвергается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        source_id = await _setup(async_client, headers, sessionmaker, "0004")
        await _plan_item(async_client, headers, source_id)
        response = await async_client.post(
            f"{_API}/monitoring-plan",
            json={
                "source_id": source_id,
                "substance": "Азота диоксид",
                "periodicity_months": 6,
                "next_due_on": str(date.today()),
            },
            headers=headers,
        )
        # 422 — как на дубль кода ФККО и номера источника: в этом модуле
        # отказ по смыслу данных отвечает одним кодом.
        assert response.status_code == 422, response.text

    async def test_то_же_вещество_на_другом_источнике_принимается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        facility_id = await _facility(async_client, headers, "0005")
        first = await _source(async_client, headers, facility_id, "0005")
        second = await _source(async_client, headers, facility_id, "0006")
        await _plan_item(async_client, headers, first)
        # Одно и то же вещество замеряют на РАЗНЫХ источниках — это норма.
        await _plan_item(async_client, headers, second)

    async def test_просроченный_замер_назван_словами(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        source_id = await _setup(async_client, headers, sessionmaker, "0007")
        await _plan_item(
            async_client,
            headers,
            source_id,
            next_due_on=date.today() - timedelta(days=10),
        )
        listed = await async_client.get(f"{_API}/monitoring-plan", headers=headers)
        assert listed.status_code == 200, listed.text
        item = listed.json()["items"][0]
        assert item["status"] == "overdue"
        assert item["status_label"] == "Замер просрочен"

    async def test_близкий_срок_замера_назван_словами(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        source_id = await _setup(async_client, headers, sessionmaker, "0008")
        await _plan_item(
            async_client,
            headers,
            source_id,
            next_due_on=date.today() + timedelta(days=10),
        )
        listed = await async_client.get(f"{_API}/monitoring-plan", headers=headers)
        item = listed.json()["items"][0]
        assert item["status"] == "due_soon"
        assert item["status_label"] == "Скоро замер"


class TestЗамерыИСравнениеСНормативом:
    async def test_превышение_норматива_это_факт_сравнения(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        source_id = await _setup(async_client, headers, sessionmaker, "0009")
        await _norm(async_client, headers, source_id, grams="0.025000")
        created = await async_client.post(
            f"{_API}/emission-measurements",
            json={
                "source_id": source_id,
                "substance": "Азота диоксид",
                "measured_on": str(date.today() - timedelta(days=3)),
                "value_grams_per_second": "0.031000",
                "protocol_number": "П-2026-014",
            },
            headers=headers,
        )
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["comparison"] == "exceeded"
        assert body["comparison_label"] == "Превышение норматива"
        assert body["norm_grams_per_second"] == "0.025000"

    async def test_замер_в_пределах_норматива(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        source_id = await _setup(async_client, headers, sessionmaker, "0010")
        await _norm(async_client, headers, source_id, grams="0.025000")
        created = await async_client.post(
            f"{_API}/emission-measurements",
            json={
                "source_id": source_id,
                "substance": "Азота диоксид",
                "measured_on": str(date.today()),
                "value_grams_per_second": "0.011000",
            },
            headers=headers,
        )
        assert created.status_code == 201, created.text
        assert created.json()["comparison"] == "within"
        assert created.json()["comparison_label"] == "В пределах норматива"

    async def test_без_норматива_это_не_превышение(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Молчание о нормативе нельзя выдавать за нарушение."""

        headers = await make_auth_headers()
        source_id = await _setup(async_client, headers, sessionmaker, "0011")
        created = await async_client.post(
            f"{_API}/emission-measurements",
            json={
                "source_id": source_id,
                "substance": "Взвешенные вещества",
                "measured_on": str(date.today()),
                "value_grams_per_second": "9.500000",
            },
            headers=headers,
        )
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["comparison"] == "no_norm"
        assert body["comparison_label"] == "Норматив не внесён"
        assert body["norm_grams_per_second"] is None

    async def test_норматив_только_валовый_сравнивать_не_с_чем(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """т/год с разовым замером в г/с не сопоставим — и врать об этом нельзя."""

        headers = await make_auth_headers()
        source_id = await _setup(async_client, headers, sessionmaker, "0012")
        await _norm(async_client, headers, source_id, grams=None, tons="1.200")
        created = await async_client.post(
            f"{_API}/emission-measurements",
            json={
                "source_id": source_id,
                "substance": "Азота диоксид",
                "measured_on": str(date.today()),
                "value_grams_per_second": "0.400000",
            },
            headers=headers,
        )
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["comparison"] == "no_single_limit"
        assert body["comparison_label"] == "Разовый норматив не внесён"

    async def test_замер_двигает_плановую_дату_вперёд(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        source_id = await _setup(async_client, headers, sessionmaker, "0013")
        due = date.today() + timedelta(days=5)
        plan_id = await _plan_item(async_client, headers, source_id, next_due_on=due)
        response = await async_client.post(
            f"{_API}/emission-measurements",
            json={
                "plan_id": plan_id,
                "source_id": source_id,
                "substance": "Азота диоксид",
                "measured_on": str(date.today()),
                "value_grams_per_second": "0.010000",
            },
            headers=headers,
        )
        assert response.status_code == 201, response.text
        listed = await async_client.get(f"{_API}/monitoring-plan", headers=headers)
        item = listed.json()["items"][0]
        assert date.fromisoformat(item["next_due_on"]) > due
        assert item["last_measured_on"] == str(date.today())

    async def test_опоздавший_замер_не_ставит_срок_в_прошлое(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Сдвиг идёт по сетке, пока срок не окажется позже самого замера."""

        headers = await make_auth_headers()
        source_id = await _setup(async_client, headers, sessionmaker, "0014")
        plan_id = await _plan_item(
            async_client,
            headers,
            source_id,
            months=3,
            next_due_on=date.today() - timedelta(days=400),
        )
        response = await async_client.post(
            f"{_API}/emission-measurements",
            json={
                "plan_id": plan_id,
                "source_id": source_id,
                "substance": "Азота диоксид",
                "measured_on": str(date.today()),
                "value_grams_per_second": "0.010000",
            },
            headers=headers,
        )
        assert response.status_code == 201, response.text
        listed = await async_client.get(f"{_API}/monitoring-plan", headers=headers)
        item = listed.json()["items"][0]
        assert date.fromisoformat(item["next_due_on"]) > date.today()
        assert item["status"] != "overdue"

    async def test_замер_задним_числом_график_не_двигает(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Внесение старых данных — не выполнение ближайшего замера."""

        headers = await make_auth_headers()
        source_id = await _setup(async_client, headers, sessionmaker, "0019")
        due = date.today() + timedelta(days=20)
        plan_id = await _plan_item(
            async_client, headers, source_id, months=3, next_due_on=due
        )
        response = await async_client.post(
            f"{_API}/emission-measurements",
            json={
                "plan_id": plan_id,
                "source_id": source_id,
                "substance": "Азота диоксид",
                "measured_on": str(date.today() - timedelta(days=700)),
                "value_grams_per_second": "0.010000",
            },
            headers=headers,
        )
        assert response.status_code == 201, response.text
        listed = await async_client.get(f"{_API}/monitoring-plan", headers=headers)
        item = listed.json()["items"][0]
        assert date.fromisoformat(item["next_due_on"]) == due

    async def test_внеплановый_замер_принимается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Замер по предписанию бывает без строки плана — отказывать нельзя."""

        headers = await make_auth_headers()
        source_id = await _setup(async_client, headers, sessionmaker, "0015")
        await _norm(async_client, headers, source_id, grams="0.025000")
        created = await async_client.post(
            f"{_API}/emission-measurements",
            json={
                "source_id": source_id,
                "substance": "Азота диоксид",
                "measured_on": str(date.today()),
                "value_grams_per_second": "0.099000",
            },
            headers=headers,
        )
        assert created.status_code == 201, created.text
        assert created.json()["plan_id"] is None
        assert created.json()["comparison"] == "exceeded"

    async def test_замер_чужого_источника_не_виден(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        source_id = await _setup(async_client, headers, sessionmaker, "0016")
        response = await async_client.post(
            f"{_API}/emission-measurements",
            json={
                "source_id": "00000000-0000-0000-0000-000000000000",
                "substance": "Азота диоксид",
                "measured_on": str(date.today()),
                "value_grams_per_second": "0.010000",
            },
            headers=headers,
        )
        assert response.status_code == 404, response.text
        assert source_id  # источник свой существует, отказ — именно по чужому


class TestСводкаИГраница:
    async def test_сводка_считает_просрочки_и_превышения(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        source_id = await _setup(async_client, headers, sessionmaker, "0017")
        await _norm(async_client, headers, source_id, grams="0.025000")
        await _plan_item(
            async_client,
            headers,
            source_id,
            next_due_on=date.today() - timedelta(days=5),
        )
        await async_client.post(
            f"{_API}/emission-measurements",
            json={
                "source_id": source_id,
                "substance": "Азота диоксид",
                "measured_on": str(date.today()),
                "value_grams_per_second": "0.500000",
            },
            headers=headers,
        )
        readiness = await async_client.get(f"{_API}/readiness", headers=headers)
        assert readiness.status_code == 200, readiness.text
        body = readiness.json()
        assert body["monitoring_plan_items"] == 1
        assert body["monitoring_overdue"] == 1
        assert body["measurements_this_year"] == 1
        assert body["measurements_exceeded"] == 1

    async def test_платформа_не_назначает_периодичность(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """ГРАНИЦА: периодичность берётся из программы ПЭК, а не из платформы."""

        headers = await make_auth_headers()
        source_id = await _setup(async_client, headers, sessionmaker, "0018")
        await _plan_item(async_client, headers, source_id)
        listed = await async_client.get(f"{_API}/monitoring-plan", headers=headers)
        item = listed.json()["items"][0]
        forbidden = {
            "required_periodicity_months",
            "recommended_periodicity_months",
            "suggested_periodicity_months",
            "pek_required",
        }
        assert forbidden.isdisjoint(item.keys())
        readiness = await async_client.get(f"{_API}/readiness", headers=headers)
        assert forbidden.isdisjoint(readiness.json().keys())


class TestТиповыеПериодичностиНаФронте:
    """Срез-101: подсказка «типовые сроки» у поля периодичности.

    Форма плана ПЭК не ограничивает выбор четырьмя значениями (сервер
    принимает 1–60 месяцев), но подсказывает те же типовые сроки, что
    подписывает бэкенд. Разойдись подписи — человек читал бы в подсказке
    «раз в квартал» там, где реестр пишет другое.
    """

    def test_типовые_сроки_на_фронте_совпадают_с_бэкендом(self) -> None:
        text = _FRONTEND_ECOLOGY_API.read_text(encoding="utf-8")
        block = re.search(
            r"MONITORING_PERIODICITY_TITLES:\s*Record<string,\s*string>\s*=\s*\{(.*?)\}",
            text,
            re.S,
        )
        assert block is not None, "не нашёлся map MONITORING_PERIODICITY_TITLES"
        front = {
            int(months): title
            for months, title in re.findall(
                r'^\s*"(\d+)":\s*"([^"]+)"', block.group(1), re.M
            )
        }
        assert front == PERIODICITY_LABELS, sorted(
            front.items() ^ PERIODICITY_LABELS.items()
        )

