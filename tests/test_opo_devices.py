"""Контур ПромБез срез-2 (Доп. №1 разд. 54.2): технические устройства и ЭПБ.

СВЕРКА, С КОТОРОЙ НАЧАЛСЯ СРЕЗ. ТЗ требует «технические устройства и
оборудование: учёт, экспертиза промышленной безопасности (ЭПБ), сроки,
диагностика, история работ». В продукте:

* ядровые ``Asset``/``Equipment`` (тогда — ``backend/app/models/assets.py``,
  весь файл 48 строк) — это ДВЕ и ТРИ колонки (имя, категория; серийный номер,
  статус), **без единой ручки API** и без единого поля срока. Учитывать по ним
  ЭПБ нечем, и никто ими не пользуется. Срез-135 удалил обе модели из кода
  (таблицы в базе остались, см. ``docs/CLEANUP_CANDIDATES.md``);
* слов «экспертиза промышленной безопасности», «ЭПБ», «диагностирование» в
  коде не было вовсе.

Устройство привязано к ОПО, а не к площадке: экспертиза и надзор идут по
зарегистрированному объекту, и на одной площадке объектов бывает несколько
(это закрыл срез-1).

ГРАНИЦА, названная и здесь, и на экране: платформа НЕ решает, нужна ли
конкретному устройству экспертиза — это зависит от типа устройства, наличия
документации и требований ФНП, которых в данных нет. Считаются ФАКТЫ,
введённые специалистом: назначенный срок службы истёк, а действующего
заключения ЭПБ нет. Тот же довод, что у интервала тренировок и обязательности
документов в контуре ПБ.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select

from app.models.feature import Feature, FeatureEnablement
from app.models.industrial_safety import OPO_DEVICE_KINDS, OPO_DEVICE_STATUSES
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


async def _facility(async_client, headers, suffix: str = "0001") -> str:
    response = await async_client.post(
        f"{_API}/facilities",
        json={
            "name": f"Объект {suffix}",
            "register_number": f"А01-90000-{suffix}",
            "hazard_class": "III",
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


class TestУчётУстройств:
    async def test_без_выдачи_модуль_невидим(self, async_client, make_auth_headers) -> None:
        headers = await make_auth_headers()
        response = await async_client.get(f"{_API}/devices", headers=headers)
        assert response.status_code == 404

    async def test_устройство_заводится_с_типом_словами(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        facility_id = await _facility(async_client, headers)
        created = await async_client.post(
            f"{_API}/devices",
            json={
                "facility_id": facility_id,
                "kind": "pressure_vessel",
                "name": "Ресивер воздушный Р-1",
                "serial_number": "12345",
                "commissioned_on": "2009-05-20",
            },
            headers=headers,
        )
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["kind_label"] == "Сосуд, работающий под давлением"
        assert body["status"] == "in_operation"
        assert body["status_label"] == "В эксплуатации"

    async def test_устройство_без_объекта_не_принимается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Экспертиза и надзор идут по зарегистрированному объекту.

        Устройство «ничьё» невозможно предъявить проверяющему: вопрос всегда
        звучит как «что эксплуатируется на объекте А01-…».
        """

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        response = await async_client.post(
            f"{_API}/devices",
            json={"kind": "boiler", "name": "Котёл"},
            headers=headers,
        )
        assert response.status_code == 422

    async def test_чужой_объект_не_подтверждается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        response = await async_client.post(
            f"{_API}/devices",
            json={
                "facility_id": "no-such-facility",
                "kind": "boiler",
                "name": "Котёл",
            },
            headers=headers,
        )
        assert response.status_code == 422
        assert "Объект не найден" in response.text

    async def test_неизвестный_тип_отвергается_словами(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        facility_id = await _facility(async_client, headers)
        response = await async_client.post(
            f"{_API}/devices",
            json={
                "facility_id": facility_id,
                "kind": "станок",
                "name": "Что-то",
            },
            headers=headers,
        )
        assert response.status_code == 422
        assert "Неизвестный тип устройства" in response.text

    async def test_вывод_из_эксплуатации_не_удаляет(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        facility_id = await _facility(async_client, headers)
        created = await async_client.post(
            f"{_API}/devices",
            json={
                "facility_id": facility_id,
                "kind": "lifting",
                "name": "Кран мостовой",
            },
            headers=headers,
        )
        patched = await async_client.patch(
            f"{_API}/devices/{created.json()['id']}",
            json={"status": "decommissioned"},
            headers=headers,
        )
        assert patched.status_code == 200, patched.text
        assert patched.json()["status_label"] == "Выведено из эксплуатации"


class TestЭкспертизаПромБезопасности:
    async def test_заключение_эпб_учитывается_со_сроком(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Заключение ЭПБ устанавливает срок дальнейшей безопасной эксплуатации."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        facility_id = await _facility(async_client, headers)
        today = date.today()
        created = await async_client.post(
            f"{_API}/devices",
            json={
                "facility_id": facility_id,
                "kind": "pipeline",
                "name": "Трубопровод пара П-3",
                "commissioned_on": "2005-01-01",
                "lifetime_until": str(today - timedelta(days=400)),
                "epb_conclusion_number": "ДЭ-03-12345-2025",
                "epb_registered_on": str(today - timedelta(days=30)),
                "epb_valid_until": str(today + timedelta(days=1400)),
            },
            headers=headers,
        )
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["epb_status"] == "ok"
        assert body["epb_status_label"] == "Заключение действует"

    async def test_просроченное_заключение_названо_просроченным(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        facility_id = await _facility(async_client, headers)
        today = date.today()
        created = await async_client.post(
            f"{_API}/devices",
            json={
                "facility_id": facility_id,
                "kind": "boiler",
                "name": "Котёл ДКВР-10",
                "epb_conclusion_number": "ДЭ-03-00001-2018",
                "epb_valid_until": str(today - timedelta(days=1)),
            },
            headers=headers,
        )
        assert created.json()["epb_status"] == "overdue"
        assert created.json()["epb_status_label"] == "Заключение просрочено"

    async def test_без_заключения_состояние_названо_отдельно(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """«Заключения нет» — это не «просрочено» и не «в порядке».

        Слить их значило бы либо обвинить исправное новое устройство, либо
        спрятать устройство, отработавшее срок службы без экспертизы.
        """

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        facility_id = await _facility(async_client, headers)
        created = await async_client.post(
            f"{_API}/devices",
            json={
                "facility_id": facility_id,
                "kind": "gas_equipment",
                "name": "Газовое оборудование ГРУ",
            },
            headers=headers,
        )
        assert created.json()["epb_status"] == "absent"
        assert created.json()["epb_status_label"] == "Заключения нет"


class TestСводкаУстройств:
    async def test_просрочки_и_отработавшие_срок_в_сводке(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        facility_id = await _facility(async_client, headers, "0002")
        today = date.today()
        before = (await async_client.get(f"{_API}/readiness", headers=headers)).json()

        # отработал назначенный срок службы, заключения нет
        await async_client.post(
            f"{_API}/devices",
            json={
                "facility_id": facility_id,
                "kind": "pressure_vessel",
                "name": "Ресивер старый",
                "lifetime_until": str(today - timedelta(days=10)),
            },
            headers=headers,
        )
        # заключение просрочено
        await async_client.post(
            f"{_API}/devices",
            json={
                "facility_id": facility_id,
                "kind": "boiler",
                "name": "Котёл с просроченным заключением",
                "epb_conclusion_number": "ДЭ-03-00002-2017",
                "epb_valid_until": str(today - timedelta(days=5)),
            },
            headers=headers,
        )

        after = (await async_client.get(f"{_API}/readiness", headers=headers)).json()
        assert after["total_devices"] == before["total_devices"] + 2
        assert after["epb_overdue"] == before["epb_overdue"] + 1
        assert (
            after["devices_past_lifetime_without_epb"]
            == before["devices_past_lifetime_without_epb"] + 1
        )

    async def test_применимость_экспертизы_не_выдумывается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """ГРАНИЦА: нужна ли устройству ЭПБ — из данных не следует.

        Новое устройство без заключения и без назначенного срока службы НЕ
        объявляется нарушением: требование ЭПБ зависит от типа устройства,
        наличия документации и норм ФНП, которых в данных нет. Сторож против
        соблазна посчитать «устройств без ЭПБ» как нарушения в следующей волне.
        """

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        facility_id = await _facility(async_client, headers, "0003")
        before = (await async_client.get(f"{_API}/readiness", headers=headers)).json()

        await async_client.post(
            f"{_API}/devices",
            json={
                "facility_id": facility_id,
                "kind": "other",
                "name": "Новое устройство без срока службы",
            },
            headers=headers,
        )
        after = (await async_client.get(f"{_API}/readiness", headers=headers)).json()
        assert after["epb_overdue"] == before["epb_overdue"]
        assert (
            after["devices_past_lifetime_without_epb"]
            == before["devices_past_lifetime_without_epb"]
        )
        # Полей-обвинений в ответе нет вовсе.
        assert "devices_without_epb" not in after
        assert "epb_required" not in after

    async def test_выведенные_из_эксплуатации_не_считаются(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Списанное устройство просрочкой быть не может — оно не работает."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        facility_id = await _facility(async_client, headers, "0004")
        today = date.today()
        created = await async_client.post(
            f"{_API}/devices",
            json={
                "facility_id": facility_id,
                "kind": "boiler",
                "name": "Котёл под списание",
                "epb_conclusion_number": "ДЭ-03-00003-2016",
                "epb_valid_until": str(today - timedelta(days=3)),
            },
            headers=headers,
        )
        before = (await async_client.get(f"{_API}/readiness", headers=headers)).json()
        await async_client.patch(
            f"{_API}/devices/{created.json()['id']}",
            json={"status": "decommissioned"},
            headers=headers,
        )
        after = (await async_client.get(f"{_API}/readiness", headers=headers)).json()
        assert after["epb_overdue"] == before["epb_overdue"] - 1
        assert after["total_devices"] == before["total_devices"] - 1


class TestИзоляцияАрендатора:
    async def test_чужое_устройство_не_правится(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        response = await async_client.patch(
            f"{_API}/devices/does-not-exist",
            json={"name": "Подмена"},
            headers=headers,
        )
        assert response.status_code == 404


class TestСловариУстройствНаФронте:
    """Срез-105: вид и состояние устройства выбирают в форме из копий словарей."""

    def test_виды_устройств_на_фронте_совпадают_с_бэкендом(self) -> None:
        front = _front_map("OPO_DEVICE_KIND_TITLES")
        assert front == OPO_DEVICE_KINDS, sorted(
            front.items() ^ OPO_DEVICE_KINDS.items()
        )

    def test_состояния_устройств_на_фронте_совпадают_с_бэкендом(self) -> None:
        front = _front_map("OPO_DEVICE_STATUS_TITLES")
        assert front == OPO_DEVICE_STATUSES, sorted(
            front.items() ^ OPO_DEVICE_STATUSES.items()
        )

