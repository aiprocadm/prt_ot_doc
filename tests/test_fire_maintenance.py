"""Контур ПБ срез-5 (Доп. №1 разд. 54.1): регламентные работы и испытания.

СВЕРКА, С КОТОРОЙ НАЧАЛСЯ СРЕЗ. У средства ПБ хранился ТОЛЬКО СЛЕДУЮЩИЙ СРОК
(``recharge_due`` / ``inspection_due``) и ни одной записи о выполненной работе:
ни даты, ни исполнителя, ни результата. Отметить «ТО проведено» можно было
единственным способом — ЗАТЕРЕТЬ срок через PATCH, и от самой работы не
оставалось следа. Инспектор же спрашивает не «когда следующая поверка», а
«покажите, что предыдущая была»; требование ТЗ «ТО систем ПБ, испытания,
устранение» было невыполнимо по построению — той же формы дыра, что у
свободной строки вида инструктажа (срез-3) и у отсутствующих тренировок
(срез-4).

Что закрывает срез:
* журнал работ ``fire_maintenance`` поверх заведённых средств: вид работы из
  ЗАКРЫТОГО словаря, дата, исполнитель, результат, замечания;
* следующий срок двигается САМОЙ ЗАПИСЬЮ о работе — срок перестаёт быть
  числом, которое можно сдвинуть без основания;
* испытания из ТЗ получили объект: пожарная лестница и противопожарный
  водопровод добавлены видами оборудования;
* аналитика ПБ: средства, у которых срок есть, а подтверждения работ нет
  НИ ОДНОГО — отдельным числом в готовности к проверке МЧС.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select

from app.models.feature import Feature, FeatureEnablement
from app.models.fire_safety import FIRE_MAINTENANCE_KINDS, FIRE_MAINTENANCE_RESULTS
from app.models.models import Tenant

_FRONTEND_FIRE_API = (
    Path(__file__).resolve().parents[1] / "frontend" / "src" / "api" / "fireSafety.ts"
)


def _front_map(name: str) -> dict[str, str]:
    """Читает map подписей из ``frontend/src/api/fireSafety.ts``."""

    text = _FRONTEND_FIRE_API.read_text(encoding="utf-8")
    block = re.search(rf"{name}:\s*Record<[^>]+>\s*=\s*\{{(.*?)\n\}}", text, re.S)
    assert block is not None, f"не нашёлся map {name}"
    return dict(re.findall(r'^\s*([A-Za-z_]+):\s*"([^"]+)"', block.group(1), re.M))


pytestmark = pytest.mark.anyio

_API = "/api/v1/fire-safety"


async def _grant(sessionmaker, code: str = "fire_safety", on: bool = True) -> None:
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


async def _unit(async_client, headers, **overrides) -> str:
    payload = {"kind": "extinguisher", "label": "ОП-5 №1"}
    payload.update(overrides)
    response = await async_client.post(f"{_API}/equipment", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["id"]


class TestЖурналРабот:
    async def test_без_выдачи_модуль_невидим(self, async_client, make_auth_headers) -> None:
        headers = await make_auth_headers()
        response = await async_client.get(f"{_API}/maintenance", headers=headers)
        assert response.status_code == 404

    async def test_работа_записывается_и_двигает_срок(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Главное правило среза: срок переносит ЗАПИСЬ О РАБОТЕ, а не правка поля."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        today = date.today()
        unit_id = await _unit(
            async_client,
            headers,
            recharge_due=str(today - timedelta(days=5)),
        )

        recorded = await async_client.post(
            f"{_API}/maintenance",
            json={
                "equipment_id": unit_id,
                "kind": "recharge",
                "performed_on": str(today),
                "performer": "ООО «Огнеборец», акт №14",
                "result": "passed",
                "next_due": str(today + timedelta(days=365)),
            },
            headers=headers,
        )
        assert recorded.status_code == 201, recorded.text
        body = recorded.json()
        assert body["kind_label"] == "Перезарядка"
        assert body["result_label"] == "Исправно"

        # срок у средства переехал сам — руками PATCH никто не делал
        unit = await async_client.get(f"{_API}/equipment", headers=headers)
        row = next(r for r in unit.json()["items"] if r["id"] == unit_id)
        assert row["recharge_due"] == str(today + timedelta(days=365))
        # и работа осталась видна в карточке средства
        assert row["last_maintenance_on"] == str(today)
        assert row["last_maintenance_result"] == "passed"

    async def test_поверка_двигает_свой_срок_а_не_чужой(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Перезарядка и поверка — разные сроки; путать их нельзя."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        today = date.today()
        unit_id = await _unit(
            async_client,
            headers,
            kind="alarm_system",
            label="АУПС корпус А",
            recharge_due=str(today + timedelta(days=10)),
            inspection_due=str(today - timedelta(days=1)),
        )
        response = await async_client.post(
            f"{_API}/maintenance",
            json={
                "equipment_id": unit_id,
                "kind": "inspection",
                "performed_on": str(today),
                "performer": "Инженер Петров",
                "result": "passed",
                "next_due": str(today + timedelta(days=180)),
            },
            headers=headers,
        )
        assert response.status_code == 201, response.text
        row = next(
            r
            for r in (await async_client.get(f"{_API}/equipment", headers=headers)).json()["items"]
            if r["id"] == unit_id
        )
        assert row["inspection_due"] == str(today + timedelta(days=180))
        assert row["recharge_due"] == str(today + timedelta(days=10))

    async def test_история_накапливается_а_не_затирается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Ради этого срез и делался: предыдущие работы остаются доказательством."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        today = date.today()
        unit_id = await _unit(async_client, headers, label="ОУ-3 №7")
        for shift in (400, 30):
            response = await async_client.post(
                f"{_API}/maintenance",
                json={
                    "equipment_id": unit_id,
                    "kind": "inspection",
                    "performed_on": str(today - timedelta(days=shift)),
                    "performer": "Подрядчик",
                    "result": "passed",
                },
                headers=headers,
            )
            assert response.status_code == 201, response.text

        listed = await async_client.get(
            f"{_API}/maintenance", params={"equipment_id": unit_id}, headers=headers
        )
        assert listed.status_code == 200
        assert listed.json()["total"] == 2
        # свежая работа — первой; «последняя» считается по ДАТЕ РАБОТЫ, а не по
        # порядку внесения (задним числом вносят чаще, чем кажется)
        assert listed.json()["items"][0]["performed_on"] == str(today - timedelta(days=30))

    async def test_неизвестный_вид_работы_отвергается_словами(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        unit_id = await _unit(async_client, headers)
        response = await async_client.post(
            f"{_API}/maintenance",
            json={
                "equipment_id": unit_id,
                "kind": "покрасить",
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
        """Запись о работе — свидетельство, а не план."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        unit_id = await _unit(async_client, headers)
        response = await async_client.post(
            f"{_API}/maintenance",
            json={
                "equipment_id": unit_id,
                "kind": "test",
                "performed_on": str(date.today() + timedelta(days=1)),
                "result": "passed",
            },
            headers=headers,
        )
        assert response.status_code == 422
        assert "будущем" in response.text

    async def test_отрицательный_результат_срок_не_двигает(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Испытание провалено — значит средство НЕ исправно.

        Перенос срока по проваленной работе означал бы «всё в порядке до
        следующего раза»: просрочка исчезла бы с экрана, а неисправность
        осталась. Поэтому срок двигают только успех и «с замечаниями».
        """

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        today = date.today()
        unit_id = await _unit(
            async_client,
            headers,
            kind="fire_escape",
            label="Лестница П1, ось А",
            inspection_due=str(today - timedelta(days=2)),
        )
        response = await async_client.post(
            f"{_API}/maintenance",
            json={
                "equipment_id": unit_id,
                "kind": "test",
                "performed_on": str(today),
                "performer": "Лаборатория",
                "result": "failed",
                "notes": "Прогиб ступени сверх нормы",
                "next_due": str(today + timedelta(days=365)),
            },
            headers=headers,
        )
        assert response.status_code == 201, response.text
        row = next(
            r
            for r in (await async_client.get(f"{_API}/equipment", headers=headers)).json()["items"]
            if r["id"] == unit_id
        )
        assert row["inspection_due"] == str(today - timedelta(days=2))
        assert row["last_maintenance_result"] == "failed"


class TestИспытанияИзТЗ:
    async def test_лестница_и_водопровод_заводятся(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """ТЗ называет испытания пожарных лестниц и водопровода — им нужен объект."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        for kind, label in (
            ("fire_escape", "Наружная пожарная лестница П1"),
            ("water_supply", "Наружный противопожарный водопровод, ПГ-3"),
        ):
            response = await async_client.post(
                f"{_API}/equipment",
                json={"kind": kind, "label": label},
                headers=headers,
            )
            assert response.status_code == 201, response.text


class TestГотовностьКПроверке:
    async def test_средства_без_подтверждения_работ_названы_числом(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Срок стоит, а доказательства работ нет ни одного — это отдельный риск."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        today = date.today()
        before = (await async_client.get(f"{_API}/readiness", headers=headers)).json()

        unit_id = await _unit(
            async_client,
            headers,
            label="ОП-8 №3",
            inspection_due=str(today + timedelta(days=90)),
        )
        after = (await async_client.get(f"{_API}/readiness", headers=headers)).json()
        assert after["units_without_maintenance"] == before["units_without_maintenance"] + 1

        await async_client.post(
            f"{_API}/maintenance",
            json={
                "equipment_id": unit_id,
                "kind": "inspection",
                "performed_on": str(today),
                "performer": "Инженер",
                "result": "passed",
            },
            headers=headers,
        )
        closed = (await async_client.get(f"{_API}/readiness", headers=headers)).json()
        assert closed["units_without_maintenance"] == before["units_without_maintenance"]


class TestИзоляцияАрендатора:
    async def test_чужое_средство_не_принимается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        response = await async_client.post(
            f"{_API}/maintenance",
            json={
                "equipment_id": "no-such-unit",
                "kind": "inspection",
                "performed_on": str(date.today()),
                "result": "passed",
            },
            headers=headers,
        )
        assert response.status_code == 404


class TestСловариРаботНаФронте:
    """Срез-103: вид работы и результат выбирают в форме из копий словарей.

    Результат решает, перенесётся ли срок средства (исправное — да,
    «неисправно» — нет), поэтому расхождение подписей опаснее обычного: человек
    выбрал бы не то, что имел в виду.
    """

    def test_виды_работ_на_фронте_совпадают_с_бэкендом(self) -> None:
        front = _front_map("FIRE_MAINTENANCE_KIND_TITLES")
        assert front == FIRE_MAINTENANCE_KINDS, sorted(
            front.items() ^ FIRE_MAINTENANCE_KINDS.items()
        )

    def test_результаты_работ_на_фронте_совпадают_с_бэкендом(self) -> None:
        front = _front_map("FIRE_MAINTENANCE_RESULT_TITLES")
        assert front == FIRE_MAINTENANCE_RESULTS, sorted(
            front.items() ^ FIRE_MAINTENANCE_RESULTS.items()
        )
