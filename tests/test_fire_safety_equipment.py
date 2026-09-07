"""Контур ПБ срез-1 (Доп. №1 разд. 54.1): первичные средства и сроки.

Первые СОБСТВЕННЫЕ ручки дисциплины: учёт огнетушителей/кранов/щитов и систем
(АУПС/АУПТ/СОУЭ) с регламентными сроками. Сводка ``/fire-safety/readiness``
отвечает на вопрос инспектора МЧС «что у вас просрочено» одним запросом и
считает просрочку ПРИ ЧТЕНИИ (не фоновой задачей — та ходит по расписанию
или падает, и всё это время сводка показывала бы вчерашнюю правду).

Гейт модуля — роутерный (разд. 61.3): до выдачи модуль невидим (404), после
выдачи работает, у отключённого читается (read-only наследуется от BIZ-61).
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select

from app.models.feature import Feature, FeatureEnablement
from app.models.fire_safety import FIRE_EQUIPMENT_KINDS
from app.models.models import Tenant

_FRONTEND_FIRE_API = (
    Path(__file__).resolve().parents[1] / "frontend" / "src" / "api" / "fireSafety.ts"
)

pytestmark = pytest.mark.anyio

_API = "/api/v1/fire-safety"


async def _grant(sessionmaker, code: str = "fire_safety", on: bool = True) -> None:
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


class TestПервичныеСредства:
    async def test_без_выдачи_модуль_невидим(self, async_client, make_auth_headers) -> None:
        headers = await make_auth_headers()
        response = await async_client.get(f"{_API}/equipment", headers=headers)
        assert response.status_code == 404

    async def test_учёт_и_сводка_готовности(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        today = date.today()

        # просроченная перезарядка
        overdue = await async_client.post(
            f"{_API}/equipment",
            json={
                "kind": "extinguisher",
                "label": "ОП-5 №1",
                "location": "Цех 1",
                "recharge_due": str(today - timedelta(days=3)),
            },
            headers=headers,
        )
        assert overdue.status_code == 201, overdue.text

        # поверка скоро (в горизонте 30 дней)
        soon = await async_client.post(
            f"{_API}/equipment",
            json={
                "kind": "alarm_system",
                "label": "АУПС корпус А",
                "inspection_due": str(today + timedelta(days=10)),
            },
            headers=headers,
        )
        assert soon.status_code == 201, soon.text

        # всё в порядке
        ok = await async_client.post(
            f"{_API}/equipment",
            json={
                "kind": "hydrant",
                "label": "ПК-1",
                "inspection_due": str(today + timedelta(days=200)),
            },
            headers=headers,
        )
        assert ok.status_code == 201, ok.text

        listed = await async_client.get(f"{_API}/equipment", headers=headers)
        assert listed.status_code == 200
        assert listed.json()["total"] >= 3

        readiness = await async_client.get(f"{_API}/readiness", headers=headers)
        assert readiness.status_code == 200, readiness.text
        body = readiness.json()
        assert body["overdue_recharge"] >= 1
        assert body["due_soon"] >= 1
        assert body["due_soon_days"] == 30

    async def test_неизвестный_вид_отвергается_словами(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        response = await async_client.post(
            f"{_API}/equipment",
            json={"kind": "teleport", "label": "X"},
            headers=headers,
        )
        assert response.status_code == 422
        assert "Неизвестный вид" in response.text

    async def test_чужая_площадка_не_подтверждается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        response = await async_client.post(
            f"{_API}/equipment",
            json={"kind": "shield", "label": "Щит-1", "site_id": "no-such-site"},
            headers=headers,
        )
        assert response.status_code == 422
        assert "Площадка не найдена" in response.text

    async def test_срок_правится_и_уходит_из_просрочки(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Перезарядили огнетушитель → выставили новый срок → сводка чиста."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        today = date.today()
        created = await async_client.post(
            f"{_API}/equipment",
            json={
                "kind": "extinguisher",
                "label": "ОУ-3 №7",
                "recharge_due": str(today - timedelta(days=1)),
            },
            headers=headers,
        )
        assert created.status_code == 201
        unit_id = created.json()["id"]

        before = (await async_client.get(f"{_API}/readiness", headers=headers)).json()

        patched = await async_client.patch(
            f"{_API}/equipment/{unit_id}",
            json={"recharge_due": str(today + timedelta(days=365))},
            headers=headers,
        )
        assert patched.status_code == 200, patched.text

        after = (await async_client.get(f"{_API}/readiness", headers=headers)).json()
        assert after["overdue_recharge"] == before["overdue_recharge"] - 1


class TestСловарьВидовСредствНаФронте:
    """Срез-103: вид средства выбирают в форме из копии словаря на фронте.

    Подписи ``FIRE_EQUIPMENT_TITLES`` в ``api/fireSafety.ts`` существовали и
    раньше (для реестра), но теперь из них СТРОИТСЯ выпадающий список: вид,
    добавленный только на бэкенде, стало нельзя выбрать вовсе.
    """

    def test_виды_средств_на_фронте_совпадают_с_бэкендом(self) -> None:
        text = _FRONTEND_FIRE_API.read_text(encoding="utf-8")
        block = re.search(
            r"FIRE_EQUIPMENT_TITLES:\s*Record<[^>]+>\s*=\s*\{(.*?)\n\}", text, re.S
        )
        assert block is not None, "не нашёлся map FIRE_EQUIPMENT_TITLES"
        front = set(re.findall(r'^\s*([a-z_]+):', block.group(1), re.M))
        assert front == set(FIRE_EQUIPMENT_KINDS), sorted(
            front ^ set(FIRE_EQUIPMENT_KINDS)
        )

