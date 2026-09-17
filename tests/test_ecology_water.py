"""Контур экологии срез-5 (Доп. №1 разд. 55.2): водопользование.

Требование: «Водопользование: водопотребление/водоотведение, разрешения,
учёт». Это последняя незакрытая часть разд. 55.2 — отходы (срез-2), выбросы
(срез-3) и ПЭК (срез-4) уже сделаны.

СВЕРКА. Ни точек водопользования, ни учёта объёмов в продукте не было: слова
«водопользование», «водозабор», «водоотведение» по бэкенду не встречались
нигде, кроме перечня коммуникаций в наряде-допуске («Водопровод /
канализация») — это про другое.

Решения:

* **точка водопользования — своя сущность**, а не поле объекта НВОС: у одного
  объекта бывает и водозабор из реки, и выпуск сточных вод, и у каждого свой
  номер, своё разрешение и свой учёт;
* **водозабор и сброс — один реестр с закрытым типом**, а не две таблицы: поля
  у них одни и те же (номер, водный объект, разрешение, объёмы), а разделение
  по типу нужно ровно для того, чтобы объёмы не смешивались в сводке;
* **единица учёта — месяц**: журнал водопользования ведётся помесячно, поэтому
  «точка + год + месяц» уникальна. Две записи за один месяц по одной точке —
  это ошибка ввода, а не два разных факта;
* **основание учёта из закрытого словаря** (прибор учёта или расчётный метод):
  это первое, что спрашивает надзор, и свободный текст здесь превращается в
  «как записали», а не «чем меряли».

ГРАНИЦА: платформа НЕ определяет, требуется ли разрешение (договор
водопользования, решение о предоставлении водного объекта), и НЕ рассчитывает
норматив допустимого сброса — его устанавливает орган по проекту НДС. Лимит
хранится как внесённый, превышение — факт сравнения внесённых чисел.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select

from app.models.ecology import MONTH_TITLES, WATER_POINT_KINDS, WATER_RECORD_BASES
from app.models.feature import Feature, FeatureEnablement
from app.models.models import Tenant

pytestmark = pytest.mark.anyio

_API = "/api/v1/ecology"
_FRONTEND_ECOLOGY_API = (
    Path(__file__).resolve().parents[1] / "frontend" / "src" / "api" / "ecology.ts"
)


def _front_map(name: str) -> dict[str, str]:
    """Читает map подписей из ``frontend/src/api/ecology.ts``."""

    text = _FRONTEND_ECOLOGY_API.read_text(encoding="utf-8")
    block = re.search(rf"{name}:\s*Record<string,\s*string>\s*=\s*\{{(.*?)\}}", text, re.S)
    assert block is not None, f"не нашёлся map {name}"
    return dict(re.findall(r'^\s*"?([A-Za-z_0-9]+)"?:\s*"([^"]+)"', block.group(1), re.M))


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


async def _point(
    async_client,
    headers,
    facility_id: str,
    *,
    number: str = "В-1",
    kind: str = "intake",
    limit: str | None = None,
    valid_until: date | None = None,
) -> str:
    payload: dict[str, object] = {
        "facility_id": facility_id,
        "point_number": number,
        "name": "Скважина №1",
        "kind": kind,
    }
    if limit is not None:
        payload["annual_limit_cubic_meters"] = limit
    if valid_until is not None:
        payload["permit_valid_until"] = str(valid_until)
    response = await async_client.post(f"{_API}/water-points", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _setup(async_client, headers, sessionmaker, suffix: str = "0001") -> str:
    await _grant(sessionmaker)
    return await _facility(async_client, headers, suffix)


class TestТочкиВодопользования:
    async def test_без_выдачи_модуль_невидим(self, async_client, make_auth_headers) -> None:
        headers = await make_auth_headers()
        response = await async_client.get(f"{_API}/water-points", headers=headers)
        assert response.status_code == 404

    async def test_точка_заводится_с_типом_словами(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        facility_id = await _setup(async_client, headers, sessionmaker)
        created = await async_client.post(
            f"{_API}/water-points",
            json={
                "facility_id": facility_id,
                "point_number": "В-1",
                "name": "Скважина №1",
                "kind": "intake",
                "water_body": "Подземный водоносный горизонт",
                "permit_number": "МОС-00123-ВХ",
                "permit_valid_until": str(date.today() + timedelta(days=400)),
                "annual_limit_cubic_meters": "12000.000",
            },
            headers=headers,
        )
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["kind_label"] == "Водозабор"
        assert body["permit_status_label"] == "Действует"

    async def test_неизвестный_тип_отвергается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        facility_id = await _setup(async_client, headers, sessionmaker, "0002")
        response = await async_client.post(
            f"{_API}/water-points",
            json={
                "facility_id": facility_id,
                "point_number": "В-2",
                "name": "Что-то",
                "kind": "труба",
            },
            headers=headers,
        )
        assert response.status_code == 422, response.text

    async def test_номер_точки_уникален_в_пределах_объекта(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        facility_id = await _setup(async_client, headers, sessionmaker, "0003")
        await _point(async_client, headers, facility_id)
        response = await async_client.post(
            f"{_API}/water-points",
            json={
                "facility_id": facility_id,
                "point_number": "В-1",
                "name": "Другая скважина",
                "kind": "discharge",
            },
            headers=headers,
        )
        assert response.status_code == 422, response.text

    async def test_тот_же_номер_на_другом_объекте_принимается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        first = await _setup(async_client, headers, sessionmaker, "0004")
        second = await _facility(async_client, headers, "0005")
        await _point(async_client, headers, first)
        await _point(async_client, headers, second)

    async def test_пустой_срок_разрешения_это_не_просрочка(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Забор из городского водопровода идёт по договору без срока."""

        headers = await make_auth_headers()
        facility_id = await _setup(async_client, headers, sessionmaker, "0006")
        await _point(async_client, headers, facility_id)
        listed = await async_client.get(f"{_API}/water-points", headers=headers)
        item = listed.json()["items"][0]
        assert item["permit_status"] == "ok"
        assert item["permit_valid_until"] is None

    async def test_просроченное_разрешение_названо_словами(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        facility_id = await _setup(async_client, headers, sessionmaker, "0007")
        await _point(
            async_client,
            headers,
            facility_id,
            valid_until=date.today() - timedelta(days=10),
        )
        listed = await async_client.get(f"{_API}/water-points", headers=headers)
        item = listed.json()["items"][0]
        assert item["permit_status"] == "overdue"
        assert item["permit_status_label"] == "Разрешение просрочено"


class TestУчётОбъёмов:
    async def test_запись_учёта_с_основанием_словами(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        facility_id = await _setup(async_client, headers, sessionmaker, "0008")
        point_id = await _point(async_client, headers, facility_id)
        # Год берётся ОДИН раз: посчитанный заново, он разошёлся бы с
        # отправленным, если прогон пересёк новогоднюю полночь.
        period_year = date.today().year
        created = await async_client.post(
            f"{_API}/water-records",
            json={
                "point_id": point_id,
                "period_year": period_year,
                "period_month": 3,
                "volume_cubic_meters": "845.500",
                "basis": "meter",
                "meter_number": "СВК-15 №77123",
            },
            headers=headers,
        )
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["basis_label"] == "Прибор учёта"
        assert body["period_label"] == f"март {period_year}"

    async def test_неизвестное_основание_отвергается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        facility_id = await _setup(async_client, headers, sessionmaker, "0009")
        point_id = await _point(async_client, headers, facility_id)
        response = await async_client.post(
            f"{_API}/water-records",
            json={
                "point_id": point_id,
                "period_year": date.today().year,
                "period_month": 3,
                "volume_cubic_meters": "10.000",
                "basis": "на глазок",
            },
            headers=headers,
        )
        assert response.status_code == 422, response.text

    async def test_месяц_вне_границ_отвергается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        facility_id = await _setup(async_client, headers, sessionmaker, "0010")
        point_id = await _point(async_client, headers, facility_id)
        for month in (0, 13):
            response = await async_client.post(
                f"{_API}/water-records",
                json={
                    "point_id": point_id,
                    "period_year": date.today().year,
                    "period_month": month,
                    "volume_cubic_meters": "10.000",
                    "basis": "meter",
                },
                headers=headers,
            )
            assert response.status_code == 422, response.text

    async def test_дубль_месяца_по_точке_отвергается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Две записи за один месяц — ошибка ввода, а не два разных факта."""

        headers = await make_auth_headers()
        facility_id = await _setup(async_client, headers, sessionmaker, "0011")
        point_id = await _point(async_client, headers, facility_id)
        payload = {
            "point_id": point_id,
            "period_year": date.today().year,
            "period_month": 5,
            "volume_cubic_meters": "100.000",
            "basis": "meter",
        }
        first = await async_client.post(f"{_API}/water-records", json=payload, headers=headers)
        assert first.status_code == 201, first.text
        second = await async_client.post(f"{_API}/water-records", json=payload, headers=headers)
        assert second.status_code == 422, second.text

    async def test_тот_же_месяц_на_другой_точке_принимается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        facility_id = await _setup(async_client, headers, sessionmaker, "0012")
        first = await _point(async_client, headers, facility_id, number="В-1")
        second = await _point(async_client, headers, facility_id, number="В-2", kind="discharge")
        for point_id in (first, second):
            response = await async_client.post(
                f"{_API}/water-records",
                json={
                    "point_id": point_id,
                    "period_year": date.today().year,
                    "period_month": 5,
                    "volume_cubic_meters": "100.000",
                    "basis": "calculation",
                },
                headers=headers,
            )
            assert response.status_code == 201, response.text

    async def test_запись_по_чужой_точке_не_заводится(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _setup(async_client, headers, sessionmaker, "0013")
        response = await async_client.post(
            f"{_API}/water-records",
            json={
                "point_id": "00000000-0000-0000-0000-000000000000",
                "period_year": date.today().year,
                "period_month": 5,
                "volume_cubic_meters": "1.000",
                "basis": "meter",
            },
            headers=headers,
        )
        assert response.status_code == 404, response.text


class TestСводкаИГраница:
    async def test_объёмы_считаются_раздельно_по_типу(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Забор и сброс в одну кучу не складываются — это разные величины."""

        headers = await make_auth_headers()
        facility_id = await _setup(async_client, headers, sessionmaker, "0014")
        intake = await _point(async_client, headers, facility_id, number="В-1")
        discharge = await _point(async_client, headers, facility_id, number="С-1", kind="discharge")
        year = date.today().year
        await async_client.post(
            f"{_API}/water-records",
            json={
                "point_id": intake,
                "period_year": year,
                "period_month": 1,
                "volume_cubic_meters": "1000.000",
                "basis": "meter",
            },
            headers=headers,
        )
        await async_client.post(
            f"{_API}/water-records",
            json={
                "point_id": discharge,
                "period_year": year,
                "period_month": 1,
                "volume_cubic_meters": "400.000",
                "basis": "calculation",
            },
            headers=headers,
        )
        readiness = await async_client.get(f"{_API}/readiness", headers=headers)
        body = readiness.json()
        assert body["water_points"] == 2
        assert body["water_intake_cubic_meters"] == "1000.000"
        assert body["water_discharge_cubic_meters"] == "400.000"

    async def test_превышение_лимита_это_факт_по_внесённому_лимиту(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        facility_id = await _setup(async_client, headers, sessionmaker, "0015")
        point_id = await _point(async_client, headers, facility_id, limit="500.000")
        await async_client.post(
            f"{_API}/water-records",
            json={
                "point_id": point_id,
                "period_year": date.today().year,
                "period_month": 2,
                "volume_cubic_meters": "700.000",
                "basis": "meter",
            },
            headers=headers,
        )
        readiness = await async_client.get(f"{_API}/readiness", headers=headers)
        assert readiness.json()["water_over_limit"] == 1

    async def test_без_лимита_превышения_нет(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """999 999 м³ без внесённого лимита нарушением не объявляются."""

        headers = await make_auth_headers()
        facility_id = await _setup(async_client, headers, sessionmaker, "0016")
        point_id = await _point(async_client, headers, facility_id)
        await async_client.post(
            f"{_API}/water-records",
            json={
                "point_id": point_id,
                "period_year": date.today().year,
                "period_month": 2,
                "volume_cubic_meters": "999999.000",
                "basis": "meter",
            },
            headers=headers,
        )
        readiness = await async_client.get(f"{_API}/readiness", headers=headers)
        assert readiness.json()["water_over_limit"] == 0

    async def test_платформа_не_судит_о_разрешении_и_нормативе(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """ГРАНИЦА: нужно ли разрешение и каков НДС — решает орган."""

        headers = await make_auth_headers()
        facility_id = await _setup(async_client, headers, sessionmaker, "0017")
        await _point(async_client, headers, facility_id)
        listed = await async_client.get(f"{_API}/water-points", headers=headers)
        item = listed.json()["items"][0]
        forbidden = {
            "permit_required",
            "suggested_limit_cubic_meters",
            "discharge_norm",
            "recommended_limit",
        }
        assert forbidden.isdisjoint(item.keys())
        readiness = await async_client.get(f"{_API}/readiness", headers=headers)
        assert forbidden.isdisjoint(readiness.json().keys())


class TestСловариНаФронте:
    """Срез-101: формы точки и записи строят выбор из копий словарей.

    Вид точки, основание учёта и месяц периода выбирают списком; значение,
    добавленное только на бэкенде, нельзя было бы ни выбрать, ни прочитать
    словами. Тот же приём, что у видов сроков и классов отходов.
    """

    def test_виды_точек_на_фронте_совпадают_с_бэкендом(self) -> None:
        front = _front_map("WATER_POINT_KIND_TITLES")
        assert front == WATER_POINT_KINDS, sorted(front.items() ^ WATER_POINT_KINDS.items())

    def test_основания_учёта_на_фронте_совпадают_с_бэкендом(self) -> None:
        front = _front_map("WATER_RECORD_BASIS_TITLES")
        assert front == WATER_RECORD_BASES, sorted(front.items() ^ WATER_RECORD_BASES.items())

    def test_месяцы_на_фронте_совпадают_с_бэкендом(self) -> None:
        front = {int(k): v for k, v in _front_map("MONTH_TITLES").items()}
        assert front == MONTH_TITLES, sorted(front.items() ^ MONTH_TITLES.items())
