"""Контур экологии срез-6 (Доп. №1 разд. 55.3): расчёт платы за НВОС.

Требование: «Расчёт платы за НВОС: по выбросам/сбросам/отходам, авансовые
платежи, декларация о плате». Этот срез закрывает расчёт и авансовые платежи;
декларация о плате и 2-ТП — формы документной фабрики, следующий срез.

СВЕРКА. По разд. 55.3 в продукте не было НИЧЕГО: ни ставок, ни расчёта, ни
платежей. При этом исходные данные уже собраны срезами 2–5 (отходы, выбросы с
замерами, водопользование) — расчёт был последним недостающим звеном.

Решения:

* **ставки платы вносятся, а не зашиты в код**: их устанавливает Правительство
  и меняет ежегодно постановлением — зашитый справочник гарантированно
  отстанет (тот же довод, что и у перечня загрязняющих веществ);
* **справочник ставок отдельно, строки расчёта отдельно**: одна ставка
  используется во многих строках и в разных кварталах, а копия ставки в каждой
  строке означала бы, что исправлять опечатку придётся во всех сразу;
* **ставка ищется по ГОДУ строки**: расчёт за 2026 год не имеет права взять
  ставку 2025-го — это разные постановления;
* **сумма считается при чтении** (масса × ставка × коэффициент), а не хранится:
  ставку правят задним числом чаще, чем кажется, и сохранённая сумма пережила
  бы исправление;
* **массу вносят руками**: автоматический перенос из журналов невозможен без
  подмены смысла — замер ПЭК даёт г/с, отходы считаются в тоннах за период, а
  масса для платы берётся за отчётный квартал по своим правилам.

ГРАНИЦА: платформа НЕ назначает повышающие коэффициенты (за превышение
норматива, за отсутствие ПЭК) и НЕ решает, возникает ли обязанность платы:
коэффициент устанавливается по закону и решению органа, а плательщика
определяет категория объекта. Нет ставки — сумма не считается ВООБЩЕ, а не
считается нулём: ноль читается как «платить нечего», и это было бы враньём.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import select

from app.models.ecology import FEE_IMPACT_KINDS
from app.models.feature import Feature, FeatureEnablement
from app.models.models import Tenant

pytestmark = pytest.mark.anyio

_FRONTEND_ECOLOGY_API = (
    Path(__file__).resolve().parents[1] / "frontend" / "src" / "api" / "ecology.ts"
)

_API = "/api/v1/ecology"
_YEAR = date.today().year


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


async def _rate(
    async_client,
    headers,
    *,
    year: int = _YEAR,
    kind: str = "emission",
    subject: str = "Азота диоксид",
    amount: str = "138.80",
) -> str:
    response = await async_client.post(
        f"{_API}/fee-rates",
        json={
            "year": year,
            "impact_kind": kind,
            "subject": subject,
            "rate_per_ton": amount,
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _line(
    async_client,
    headers,
    *,
    year: int = _YEAR,
    quarter: int = 1,
    kind: str = "emission",
    subject: str = "Азота диоксид",
    mass: str = "2.000",
    coefficient: str | None = None,
) -> dict:
    payload: dict[str, object] = {
        "year": year,
        "quarter": quarter,
        "impact_kind": kind,
        "subject": subject,
        "mass_tons": mass,
    }
    if coefficient is not None:
        payload["coefficient"] = coefficient
    response = await async_client.post(f"{_API}/fee-lines", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


class TestСправочникСтавок:
    async def test_без_выдачи_модуль_невидим(self, async_client, make_auth_headers) -> None:
        headers = await make_auth_headers()
        response = await async_client.get(f"{_API}/fee-rates", headers=headers)
        assert response.status_code == 404

    async def test_ставка_заводится_с_видом_воздействия_словами(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        created = await async_client.post(
            f"{_API}/fee-rates",
            json={
                "year": _YEAR,
                "impact_kind": "waste",
                "subject": "Отходы IV класса опасности",
                "rate_per_ton": "663.20",
                "source_document": "Постановление Правительства РФ",
            },
            headers=headers,
        )
        assert created.status_code == 201, created.text
        assert created.json()["impact_kind_label"] == "Размещение отходов"

    async def test_неизвестный_вид_воздействия_отвергается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        response = await async_client.post(
            f"{_API}/fee-rates",
            json={
                "year": _YEAR,
                "impact_kind": "шум",
                "subject": "Что-то",
                "rate_per_ton": "10.00",
            },
            headers=headers,
        )
        assert response.status_code == 422, response.text

    async def test_дубль_ставки_за_год_отвергается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        await _rate(async_client, headers)
        response = await async_client.post(
            f"{_API}/fee-rates",
            json={
                "year": _YEAR,
                "impact_kind": "emission",
                "subject": "Азота диоксид",
                "rate_per_ton": "999.00",
            },
            headers=headers,
        )
        assert response.status_code == 422, response.text

    async def test_та_же_ставка_на_другой_год_принимается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Ставки меняются ежегодно — это разные постановления."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        await _rate(async_client, headers, year=_YEAR)
        await _rate(async_client, headers, year=_YEAR - 1, amount="132.40")


class TestРасчётПлаты:
    async def test_сумма_это_масса_на_ставку_на_коэффициент(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        await _rate(async_client, headers, amount="100.00")
        body = await _line(async_client, headers, mass="2.500", coefficient="2.0")
        assert body["rate_per_ton"] == "100.00"
        assert body["amount_rubles"] == "500.00"
        assert body["rate_status"] == "found"

    async def test_коэффициент_по_умолчанию_единица(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        await _rate(async_client, headers, amount="100.00")
        body = await _line(async_client, headers, mass="3.000")
        assert body["coefficient"] == "1.00"
        assert body["amount_rubles"] == "300.00"

    async def test_без_ставки_сумма_не_считается_и_это_не_ноль(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Ноль читался бы как «платить нечего» — это было бы враньём."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        body = await _line(async_client, headers, subject="Углерода оксид")
        assert body["rate_status"] == "missing"
        assert body["rate_status_label"] == "Ставка не внесена"
        assert body["rate_per_ton"] is None
        assert body["amount_rubles"] is None

    async def test_ставка_чужого_года_не_подхватывается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Расчёт за этот год не имеет права взять прошлогоднюю ставку."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        await _rate(async_client, headers, year=_YEAR - 1, amount="132.40")
        body = await _line(async_client, headers, year=_YEAR)
        assert body["rate_status"] == "missing"
        assert body["amount_rubles"] is None

    async def test_квартал_вне_границ_отвергается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        for quarter in (0, 5):
            response = await async_client.post(
                f"{_API}/fee-lines",
                json={
                    "year": _YEAR,
                    "quarter": quarter,
                    "impact_kind": "emission",
                    "subject": "Азота диоксид",
                    "mass_tons": "1.000",
                },
                headers=headers,
            )
            assert response.status_code == 422, response.text

    async def test_нулевой_коэффициент_отвергается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Ноль обнулил бы плату — такого коэффициента не бывает."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        response = await async_client.post(
            f"{_API}/fee-lines",
            json={
                "year": _YEAR,
                "quarter": 1,
                "impact_kind": "emission",
                "subject": "Азота диоксид",
                "mass_tons": "1.000",
                "coefficient": "0",
            },
            headers=headers,
        )
        assert response.status_code == 422, response.text

    async def test_дубль_строки_за_квартал_отвергается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        await _line(async_client, headers)
        response = await async_client.post(
            f"{_API}/fee-lines",
            json={
                "year": _YEAR,
                "quarter": 1,
                "impact_kind": "emission",
                "subject": "Азота диоксид",
                "mass_tons": "5.000",
            },
            headers=headers,
        )
        assert response.status_code == 422, response.text

    async def test_тот_же_предмет_в_другом_квартале_принимается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        await _line(async_client, headers, quarter=1)
        await _line(async_client, headers, quarter=2)

    async def test_правка_ставки_меняет_сумму_уже_внесённой_строки(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Сумма считается при чтении: исправленная ставка доходит до строк."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        rate_id = await _rate(async_client, headers, amount="100.00")
        await _line(async_client, headers, mass="1.000")
        patched = await async_client.patch(
            f"{_API}/fee-rates/{rate_id}",
            json={"rate_per_ton": "150.00"},
            headers=headers,
        )
        assert patched.status_code == 200, patched.text
        listed = await async_client.get(f"{_API}/fee-lines", headers=headers)
        assert listed.json()["items"][0]["amount_rubles"] == "150.00"


class TestСводкаИГраница:
    async def test_сводка_считает_плату_и_строки_без_ставки(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        await _rate(async_client, headers, amount="100.00")
        await _line(async_client, headers, quarter=1, mass="2.000")
        await _line(async_client, headers, quarter=2, subject="Углерода оксид")
        readiness = await async_client.get(f"{_API}/readiness", headers=headers)
        body = readiness.json()
        assert body["fee_lines"] == 2
        assert body["fee_lines_without_rate"] == 1
        # В сумму попадает только то, что посчитано: строка без ставки не
        # прибавляет ноль, иначе итог выглядел бы полным.
        assert body["fee_total_rubles"] == "200.00"

    async def test_платформа_не_назначает_коэффициент(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """ГРАНИЦА: коэффициент — закон и решение органа, не догадка системы."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        await _rate(async_client, headers)
        await _line(async_client, headers)
        listed = await async_client.get(f"{_API}/fee-lines", headers=headers)
        item = listed.json()["items"][0]
        forbidden = {
            "suggested_coefficient",
            "recommended_coefficient",
            "fee_required",
            "payer_status",
        }
        assert forbidden.isdisjoint(item.keys())
        readiness = await async_client.get(f"{_API}/readiness", headers=headers)
        assert forbidden.isdisjoint(readiness.json().keys())

    async def test_чужая_строка_не_читается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        response = await async_client.patch(
            f"{_API}/fee-lines/00000000-0000-0000-0000-000000000000",
            json={"mass_tons": "1.000"},
            headers=headers,
        )
        assert response.status_code == 404, response.text


class TestСловарьВидовВоздействияНаФронте:
    """Срез-102: вид воздействия выбирают в формах ставки и строки расчёта.

    Оба списка строятся из ``FEE_IMPACT_KIND_TITLES`` в ``api/ecology.ts``:
    вид, добавленный только на бэкенде, нельзя было бы ни выбрать, ни
    прочитать словами — и строка расчёта по нему никогда не нашла бы ставку.
    """

    def test_виды_воздействия_на_фронте_совпадают_с_бэкендом(self) -> None:
        text = _FRONTEND_ECOLOGY_API.read_text(encoding="utf-8")
        block = re.search(
            r"FEE_IMPACT_KIND_TITLES:\s*Record<string,\s*string>\s*=\s*\{(.*?)\}",
            text,
            re.S,
        )
        assert block is not None, "не нашёлся map FEE_IMPACT_KIND_TITLES"
        front = dict(re.findall(r'^\s*([A-Za-z_]+):\s*"([^"]+)"', block.group(1), re.M))
        assert front == FEE_IMPACT_KINDS, sorted(front.items() ^ FEE_IMPACT_KINDS.items())
