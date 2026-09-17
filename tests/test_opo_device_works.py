"""Контур ПромБез срез-3 (Доп. №1 разд. 54.2): диагностика и история работ.

СВЕРКА, С КОТОРОЙ НАЧАЛСЯ СРЕЗ. Срез-2 завёл устройства со сроками — назначенным
сроком службы и сроком из заключения ЭПБ, — но не завёл НИ ОДНОЙ записи о том,
что с устройством делали. Следствие ровно то же, что было у пожарного
оборудования до его журнала работ: отметить проведённую экспертизу или
диагностирование можно единственным способом — ЗАТЕРЕТЬ срок правкой поля, и от
работы не остаётся следа. Инспектор Ростехнадзора спрашивает не «когда
следующая экспертиза», а «покажите заключение по предыдущей».

Что закрывает срез:
* журнал работ по устройству: вид из ЗАКРЫТОГО словаря (диагностирование,
  освидетельствование, ЭПБ, ТО, ремонт), дата, исполнитель, результат,
  замечания;
* **заключение ЭПБ вносится записью о работе** и само переносит срок
  дальнейшей безопасной эксплуатации — срок перестаёт быть числом, которое
  можно сдвинуть без основания;
* отрицательный результат срок НЕ переносит: «неисправно, но эксплуатировать
  ещё пять лет» — это не вывод экспертизы;
* аналитика: устройства, по которым нет НИ ОДНОЙ записи о работах.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select

from app.models.feature import Feature, FeatureEnablement
from app.models.industrial_safety import OPO_WORK_KINDS, OPO_WORK_RESULTS
from app.models.models import Tenant

pytestmark = pytest.mark.anyio

_API = "/api/v1/industrial-safety"


_FRONTEND_OPO_API = (
    Path(__file__).resolve().parents[1] / "frontend" / "src" / "api" / "industrialSafety.ts"
)


def _front_map(name: str) -> dict[str, str]:
    """Читает map подписей из ``frontend/src/api/industrialSafety.ts``."""

    text = _FRONTEND_OPO_API.read_text(encoding="utf-8")
    block = re.search(rf"{name}:\s*Record<[^>]+>\s*=\s*\{{(.*?)\n\}}", text, re.S)
    assert block is not None, f"не нашёлся map {name}"
    return dict(re.findall(r'^\s*([A-Za-z_]+):\s*"([^"]+)"', block.group(1), re.M))


async def _grant(sessionmaker, code: str = "industrial_safety", on: bool = True) -> None:
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


async def _device(async_client, headers, suffix: str = "0001", **overrides) -> str:
    facility = await async_client.post(
        f"{_API}/facilities",
        json={
            "name": f"Объект {suffix}",
            "register_number": f"А01-70000-{suffix}",
            "hazard_class": "III",
        },
        headers=headers,
    )
    assert facility.status_code == 201, facility.text
    payload = {
        "facility_id": facility.json()["id"],
        "kind": "pressure_vessel",
        "name": f"Устройство {suffix}",
    }
    payload.update(overrides)
    response = await async_client.post(f"{_API}/devices", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["id"]


class TestЖурналРабот:
    async def test_без_выдачи_модуль_невидим(self, async_client, make_auth_headers) -> None:
        headers = await make_auth_headers()
        response = await async_client.get(f"{_API}/device-works", headers=headers)
        assert response.status_code == 404

    async def test_заключение_эпб_вносится_записью_и_двигает_срок(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Главное правило среза: срок переносит ЗАКЛЮЧЕНИЕ, а не правка поля."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        today = date.today()
        device_id = await _device(
            async_client,
            headers,
            lifetime_until=str(today - timedelta(days=200)),
        )

        recorded = await async_client.post(
            f"{_API}/device-works",
            json={
                "device_id": device_id,
                "kind": "epb",
                "performed_on": str(today),
                "performer": "ООО «ЭкспертПром», аттестат №1234",
                "result": "passed",
                "conclusion_number": "ДЭ-03-55555-2026",
                "next_due": str(today + timedelta(days=1825)),
            },
            headers=headers,
        )
        assert recorded.status_code == 201, recorded.text
        body = recorded.json()
        assert body["kind_label"] == "Экспертиза промышленной безопасности"
        assert body["result_label"] == "Пригодно к эксплуатации"
        assert body["shifted_due"] is True

        # срок и реквизиты заключения переехали в карточку устройства сами
        listed = await async_client.get(f"{_API}/devices", headers=headers)
        row = next(r for r in listed.json()["items"] if r["id"] == device_id)
        assert row["epb_valid_until"] == str(today + timedelta(days=1825))
        assert row["epb_conclusion_number"] == "ДЭ-03-55555-2026"
        assert row["epb_registered_on"] == str(today)
        assert row["epb_status"] == "ok"
        assert row["last_work_on"] == str(today)

    async def test_отрицательное_заключение_срок_не_двигает(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """«Неисправно, но эксплуатировать ещё пять лет» — не вывод экспертизы."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        today = date.today()
        device_id = await _device(async_client, headers, "0002")

        response = await async_client.post(
            f"{_API}/device-works",
            json={
                "device_id": device_id,
                "kind": "epb",
                "performed_on": str(today),
                "result": "failed",
                "conclusion_number": "ДЭ-03-66666-2026",
                "next_due": str(today + timedelta(days=1825)),
                "notes": "Выявлены недопустимые дефекты корпуса",
            },
            headers=headers,
        )
        assert response.status_code == 201, response.text
        assert response.json()["shifted_due"] is False

        listed = await async_client.get(f"{_API}/devices", headers=headers)
        row = next(r for r in listed.json()["items"] if r["id"] == device_id)
        assert row["epb_valid_until"] is None
        assert row["epb_status"] == "absent"

    async def test_диагностирование_срок_эпб_не_трогает(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Диагностирование — не экспертиза: продлевать эксплуатацию им нельзя.

        Заключение о возможности дальнейшей эксплуатации даёт только ЭПБ;
        если бы срок двигала любая работа, «протёрли и записали ТО»
        продлевало бы жизнь устройству на бумаге.
        """

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        today = date.today()
        device_id = await _device(async_client, headers, "0003")

        response = await async_client.post(
            f"{_API}/device-works",
            json={
                "device_id": device_id,
                "kind": "diagnostics",
                "performed_on": str(today),
                "result": "passed",
                "next_due": str(today + timedelta(days=365)),
            },
            headers=headers,
        )
        assert response.status_code == 201, response.text
        assert response.json()["shifted_due"] is False

        listed = await async_client.get(f"{_API}/devices", headers=headers)
        row = next(r for r in listed.json()["items"] if r["id"] == device_id)
        assert row["epb_valid_until"] is None

    async def test_история_накапливается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        today = date.today()
        device_id = await _device(async_client, headers, "0004")
        for shift in (900, 30):
            response = await async_client.post(
                f"{_API}/device-works",
                json={
                    "device_id": device_id,
                    "kind": "technical_survey",
                    "performed_on": str(today - timedelta(days=shift)),
                    "result": "passed",
                },
                headers=headers,
            )
            assert response.status_code == 201, response.text

        listed = await async_client.get(
            f"{_API}/device-works", params={"device_id": device_id}, headers=headers
        )
        assert listed.json()["total"] == 2
        # «последняя» — по ДАТЕ РАБОТЫ, а не по порядку внесения
        assert listed.json()["items"][0]["performed_on"] == str(today - timedelta(days=30))

    async def test_неизвестный_вид_работы_отвергается_словами(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        device_id = await _device(async_client, headers, "0005")
        response = await async_client.post(
            f"{_API}/device-works",
            json={
                "device_id": device_id,
                "kind": "покраска",
                "performed_on": str(date.today()),
                "result": "passed",
            },
            headers=headers,
        )
        assert response.status_code == 422
        assert "Неизвестный вид работы" in response.text

    async def test_работа_в_будущем_не_принимается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        device_id = await _device(async_client, headers, "0006")
        response = await async_client.post(
            f"{_API}/device-works",
            json={
                "device_id": device_id,
                "kind": "maintenance",
                "performed_on": str(date.today() + timedelta(days=1)),
                "result": "passed",
            },
            headers=headers,
        )
        assert response.status_code == 422
        assert "будущем" in response.text

    async def test_эпб_без_номера_заключения_не_принимается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Экспертиза без номера заключения не существует как документ.

        Именно номер вносится в реестр Ростехнадзора и предъявляется
        проверяющему; запись «экспертиза была» без него ничего не доказывает.
        """

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        device_id = await _device(async_client, headers, "0007")
        response = await async_client.post(
            f"{_API}/device-works",
            json={
                "device_id": device_id,
                "kind": "epb",
                "performed_on": str(date.today()),
                "result": "passed",
            },
            headers=headers,
        )
        assert response.status_code == 422
        assert "номер заключения" in response.text


class TestСводкаРабот:
    async def test_устройства_без_записей_названы_числом(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        before = (await async_client.get(f"{_API}/readiness", headers=headers)).json()

        device_id = await _device(async_client, headers, "0008")
        after = (await async_client.get(f"{_API}/readiness", headers=headers)).json()
        assert after["devices_without_work_record"] == before["devices_without_work_record"] + 1

        await async_client.post(
            f"{_API}/device-works",
            json={
                "device_id": device_id,
                "kind": "maintenance",
                "performed_on": str(date.today()),
                "result": "passed",
            },
            headers=headers,
        )
        closed = (await async_client.get(f"{_API}/readiness", headers=headers)).json()
        assert closed["devices_without_work_record"] == before["devices_without_work_record"]


class TestИзоляцияАрендатора:
    async def test_чужое_устройство_не_принимается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        response = await async_client.post(
            f"{_API}/device-works",
            json={
                "device_id": "no-such-device",
                "kind": "maintenance",
                "performed_on": str(date.today()),
                "result": "passed",
            },
            headers=headers,
        )
        assert response.status_code == 404


class TestСловариРаботНаФронте:
    """Срез-105: вид работы и результат выбирают в форме из копий словарей.

    Вид решает, продлит ли работа срок эксплуатации (продлевает только
    экспертиза), поэтому расхождение подписей опаснее обычного: человек выбрал
    бы не то, что имел в виду.
    """

    def test_виды_работ_на_фронте_совпадают_с_бэкендом(self) -> None:
        front = _front_map("OPO_WORK_KIND_TITLES")
        assert front == OPO_WORK_KINDS, sorted(front.items() ^ OPO_WORK_KINDS.items())

    def test_результаты_работ_на_фронте_совпадают_с_бэкендом(self) -> None:
        front = _front_map("OPO_WORK_RESULT_TITLES")
        assert front == OPO_WORK_RESULTS, sorted(front.items() ^ OPO_WORK_RESULTS.items())
