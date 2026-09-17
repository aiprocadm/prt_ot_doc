"""Подсказки мастера для отчётности экологии (продолжение решения владельца).

Приём отработан на БДД: подсказка приходит из реестра, но НЕ становится
ответом — отчёт подписывает специалист. Здесь тот же механизм для экологии,
и он вскрывает два вопроса, которых у БДД не было.

**ПЕРВЫЙ: какой период считать.** У БДД окно СКОЛЬЗЯЩЕЕ (365 дней), потому что
аварийность смотрят «за последний год» в любой день. У экологии период —
КАЛЕНДАРНЫЙ год, потому что таковы формы отчётности (2-ТП и декларация
подаются за прошедший год). Одинаковое окно для обеих дисциплин было бы удобнее
в коде и неверно по существу.

Год берётся ПРОШЛЫЙ, и это решение, а не умолчание: предлагать текущий,
неполный, значило бы подсунуть заведомо неверное число. Год назван В ИСТОЧНИКЕ
— отчитывается специалист за другой, увидит и не подставит.

**ВТОРОЙ: чего подсказывать НЕЛЬЗЯ.**

* **плата за НВОС** — суммы считаются по ставкам и коэффициентам, а не по
  объёмам напрямую; разд. 55.3 прямо оставил расчёт специалисту, и подсказать
  сумму значило бы посчитать за него;
* **объект НВОС, когда их несколько** — выбрать за специалиста, о котором из
  них отчёт, платформа не может, а подсунуть первый попавшийся хуже, чем не
  подсказать вовсе.

ГРАНИЦА прежняя: подсказка не подставляется сама, у неё всегда есть источник,
и отчётный год специалист выбирает сам.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.ecology import (
    EmissionMeasurement,
    EmissionSource,
    EnvironmentalFacility,
    WasteMovement,
    WastePassport,
    WaterUsagePoint,
    WaterUsageRecord,
)
from app.models.feature import Feature, FeatureEnablement
from app.models.models import Tenant
from app.modules.packs.definitions import PACK_CODE_ECO_REPORTS

pytestmark = pytest.mark.anyio

_FIELDS = "/api/v1/packs/scenarios"
_LAST_YEAR = date.today().year - 1


async def _grant(sessionmaker, code: str = "ecology") -> None:
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
            session.add(FeatureEnablement(tenant_id=tenant.id, feature_id=feature.id, on=True))
        else:
            grant.on = True
        await session.commit()


async def _tenant_id(sessionmaker) -> str:
    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        return str(tenant.id)


async def _facility(sessionmaker, *, number: str, category: str = "II") -> str:
    async with sessionmaker() as session:
        tid = await _tenant_id(sessionmaker)
        facility = EnvironmentalFacility(
            tenant_id=tid,
            name=f"Площадка {number}",
            register_number=number,
            category=category,
            status="registered",
        )
        session.add(facility)
        await session.commit()
        return str(facility.id)


async def _waste(sessionmaker, *, kind: str, tons: str, year: int) -> None:
    async with sessionmaker() as session:
        tid = await _tenant_id(sessionmaker)
        passport = (
            (await session.execute(select(WastePassport).where(WastePassport.tenant_id == tid)))
            .scalars()
            .first()
        )
        if passport is None:
            passport = WastePassport(
                tenant_id=tid,
                name="Отход",
                fkko_code="12345678901",
                hazard_class="IV",
            )
            session.add(passport)
            await session.flush()
        session.add(
            WasteMovement(
                tenant_id=tid,
                passport_id=passport.id,
                kind=kind,
                happened_on=date(year, 6, 1),
                quantity_tons=Decimal(tons),
            )
        )
        await session.commit()


async def _fields(async_client, headers) -> dict:
    response = await async_client.get(f"{_FIELDS}/{PACK_CODE_ECO_REPORTS}/fields", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    return {f["name"]: f for f in body["fields"]} | {"__body__": body}


class TestГодПрошлый:
    async def test_считается_прошлый_год_а_не_текущий(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Отчётность сдают ЗА ПРОШЕДШИЙ год.

        Предложи платформа текущий, неполный, — специалист подставил бы
        заведомо неверное число, и заметить это было бы нечем.
        """

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        await _waste(sessionmaker, kind="generated", tons="10.5", year=_LAST_YEAR)
        await _waste(sessionmaker, kind="generated", tons="99.9", year=date.today().year)

        fields = await _fields(async_client, headers)
        assert fields["eco_waste_generated"]["suggested"] == "10.500"
        assert str(_LAST_YEAR) in fields["eco_waste_generated"]["suggested_source"]

    async def test_виды_движения_не_смешиваются(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Образование, передача и размещение — три РАЗНЫЕ строки отчёта."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        await _waste(sessionmaker, kind="generated", tons="10", year=_LAST_YEAR)
        await _waste(sessionmaker, kind="transferred", tons="4", year=_LAST_YEAR)
        await _waste(sessionmaker, kind="disposed", tons="1", year=_LAST_YEAR)

        fields = await _fields(async_client, headers)
        assert fields["eco_waste_generated"]["suggested"] == "10.000"
        assert fields["eco_waste_transferred"]["suggested"] == "4.000"
        assert fields["eco_waste_disposed"]["suggested"] == "1.000"


class TestОбъектНВОС:
    async def test_единственный_объект_подсказывается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        await _facility(sessionmaker, number="12-0177-010001-П", category="II")

        fields = await _fields(async_client, headers)
        assert fields["eco_nvos_number"]["suggested"] == "12-0177-010001-П"
        assert fields["eco_nvos_category"]["suggested"] == "II"

    async def test_нескольких_объектов_платформа_не_выбирает(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """САМОЕ ВАЖНОЕ ЗДЕСЬ.

        У организации бывает несколько объектов НВОС, и о котором из них
        отчёт — решает специалист. Подсунуть первый попавшийся хуже, чем не
        подсказать вовсе: неверный регистрационный номер в декларации
        заметить почти невозможно.
        """

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        await _facility(sessionmaker, number="12-0177-010001-П", category="II")
        await _facility(sessionmaker, number="12-0177-010002-П", category="III")

        fields = await _fields(async_client, headers)
        assert fields["eco_nvos_number"]["suggested"] is None
        assert fields["eco_nvos_category"]["suggested"] is None

    async def test_без_объектов_подсказки_нет(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        fields = await _fields(async_client, headers)
        assert fields["eco_nvos_number"]["suggested"] is None


class TestВодаИЗамеры:
    async def test_забор_и_сброс_не_складываются(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Это разные величины — так прямо сказано у словаря видов точек."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        facility_id = await _facility(sessionmaker, number="12-0177-010001-П")
        async with sessionmaker() as session:
            tid = await _tenant_id(sessionmaker)
            intake = WaterUsagePoint(
                tenant_id=tid,
                facility_id=facility_id,
                point_number="В-1",
                name="Скважина",
                kind="intake",
            )
            discharge = WaterUsagePoint(
                tenant_id=tid,
                facility_id=facility_id,
                point_number="С-1",
                name="Выпуск",
                kind="discharge",
            )
            session.add_all([intake, discharge])
            await session.flush()
            session.add_all(
                [
                    WaterUsageRecord(
                        tenant_id=tid,
                        point_id=intake.id,
                        period_year=_LAST_YEAR,
                        period_month=3,
                        volume_cubic_meters=Decimal("100"),
                        basis="meter",
                    ),
                    WaterUsageRecord(
                        tenant_id=tid,
                        point_id=discharge.id,
                        period_year=_LAST_YEAR,
                        period_month=3,
                        volume_cubic_meters=Decimal("40"),
                        basis="meter",
                    ),
                ]
            )
            await session.commit()

        fields = await _fields(async_client, headers)
        assert fields["eco_water_intake"]["suggested"] == "100.000"
        assert fields["eco_water_discharge"]["suggested"] == "40.000"

    async def test_замеры_и_источники_считаются(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        facility_id = await _facility(sessionmaker, number="12-0177-010001-П")
        async with sessionmaker() as session:
            tid = await _tenant_id(sessionmaker)
            source = EmissionSource(
                tenant_id=tid,
                facility_id=facility_id,
                source_number="0001",
                name="Труба",
                kind="organized",
            )
            session.add(source)
            await session.flush()
            session.add(
                EmissionMeasurement(
                    tenant_id=tid,
                    source_id=source.id,
                    substance="Азота диоксид",
                    measured_on=date(_LAST_YEAR, 5, 5),
                    value_grams_per_second=Decimal("0.010"),
                )
            )
            await session.commit()

        fields = await _fields(async_client, headers)
        assert fields["eco_air_sources"]["suggested"] == "1"
        assert fields["eco_pek_measurements"]["suggested"] == "1"


class TestГраница:
    async def test_плата_за_нвос_не_подсказывается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """ГРАНИЦА: суммы считаются по ставкам, а не по объёмам напрямую.

        Разд. 55.3 прямо оставил расчёт специалисту — подсказать сумму значило
        бы посчитать за него, а ошибку в плате находит уже проверка.
        """

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        await _waste(sessionmaker, kind="disposed", tons="5", year=_LAST_YEAR)
        fields = await _fields(async_client, headers)
        for key in (
            "eco_fee_emissions",
            "eco_fee_discharges",
            "eco_fee_waste",
            "eco_fee_advances",
        ):
            assert fields[key]["suggested"] is None, key

    async def test_отчётный_год_и_составитель_не_подсказываются(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """За какой год отчёт — решает специалист, а не платформа."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        fields = await _fields(async_client, headers)
        assert fields["eco_report_year"]["suggested"] is None
        assert fields["eco_responsible"]["suggested"] is None

    async def test_у_каждой_подсказки_есть_источник(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        await _facility(sessionmaker, number="12-0177-010001-П")
        fields = await _fields(async_client, headers)
        for name, field in fields.items():
            if name == "__body__" or field["suggested"] is None:
                continue
            assert field["suggested_source"], name
