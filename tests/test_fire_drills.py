"""Контур ПБ срез-4 (Доп. №1 разд. 54.1): тренировки и учения по эвакуации.

СВЕРКА, С КОТОРОЙ НАЧАЛСЯ СРЕЗ. Экран ``/fire-training`` называется
«инструктажи и **учения**», а показывал только шаблоны, журналы и просроченные
записи ИНСТРУКТАЖЕЙ — ни одной тренировки. Сущности тренировки не было вовсе:
существовал лишь шаблон документа «Программа практической тренировки по
эвакуации» в комплекте ПБ. То есть бумагу выпустить было можно, а ответить на
вопрос инспектора «когда была последняя тренировка и не просрочена ли
запланированная» — нельзя по построению. Требование ТЗ «план-график
тренировок по эвакуации, протоколы, анализ» было невыполнимо.

Что закрывает срез:
* план-график — ``planned_on`` обязателен, тренировка рождается запланированной;
* протокол — ``held_on`` + число участников + результат из ЗАКРЫТОГО словаря;
* анализ — ``findings`` (замечания и выводы);
* контроль сроков — просроченный план виден в ``/fire-safety/readiness``.

ГРАНИЦА, названная и здесь, и на экране: интервал «не реже раза в полгода»
(ППР РФ) сводка САМА не судит — он обязателен только для объектов с массовым
пребыванием людей, а признака массового пребывания у площадки в данных нет.
Считается то, что следует из данных: просроченный ПЛАН и дата последней
проведённой тренировки. Угадывать применимость нормы и красить площадку в
нарушение мы не имеем права (прецедент границ карточки 360°, срез-3).
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select

from app.models.feature import Feature, FeatureEnablement
from app.models.fire_safety import FIRE_DRILL_KINDS, FIRE_DRILL_OUTCOMES
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


class TestТренировкиПоЭвакуации:
    async def test_без_выдачи_модуль_невидим(self, async_client, make_auth_headers) -> None:
        """Гейт роутерный — новая ручка защищена по построению (разд. 61.3)."""

        headers = await make_auth_headers()
        response = await async_client.get(f"{_API}/drills", headers=headers)
        assert response.status_code == 404

    async def test_планграфик_и_протокол(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """План → проведение → протокол с результатом и анализом."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        today = date.today()

        planned = await async_client.post(
            f"{_API}/drills",
            json={
                "kind": "evacuation",
                "title": "Тренировка по эвакуации, корпус А",
                "planned_on": str(today + timedelta(days=20)),
                "scenario": "Возгорание в электрощитовой первого этажа",
            },
            headers=headers,
        )
        assert planned.status_code == 201, planned.text
        body = planned.json()
        assert body["status"] == "planned"
        assert body["held_on"] is None

        drill_id = body["id"]
        held = await async_client.patch(
            f"{_API}/drills/{drill_id}",
            json={
                "held_on": str(today),
                "participants": 48,
                "outcome": "with_remarks",
                "findings": "Эвакуация за 4 мин 10 с; второй выход был загромождён",
            },
            headers=headers,
        )
        assert held.status_code == 200, held.text
        after = held.json()
        assert after["status"] == "held"
        assert after["outcome_label"] == "Проведена с замечаниями"
        assert after["participants"] == 48

    async def test_неизвестный_вид_отвергается_словами(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Дыра среза-8 не повторяется: вид тренировки — закрытый словарь.

        Свободная строка снова сделала бы «анализ» невозможным: «эвакуация»,
        «Эвакуация», «evac» — три разных вида для любого счёта.
        """

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        response = await async_client.post(
            f"{_API}/drills",
            json={
                "kind": "teleport",
                "title": "X",
                "planned_on": str(date.today()),
            },
            headers=headers,
        )
        assert response.status_code == 422
        assert "Неизвестный вид тренировки" in response.text

    async def test_проведённая_без_результата_не_принимается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """«Провели» без результата — протокол без анализа, требование ТЗ мимо."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        today = date.today()
        created = await async_client.post(
            f"{_API}/drills",
            json={
                "kind": "evacuation",
                "title": "Тренировка, склад",
                "planned_on": str(today),
            },
            headers=headers,
        )
        assert created.status_code == 201
        response = await async_client.patch(
            f"{_API}/drills/{created.json()['id']}",
            json={"held_on": str(today)},
            headers=headers,
        )
        assert response.status_code == 422
        assert "результат" in response.text

    async def test_результат_без_проведения_не_принимается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """И наоборот: результат у непроведённой тренировки — выдумка."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        created = await async_client.post(
            f"{_API}/drills",
            json={
                "kind": "fire_fighting",
                "title": "Применение первичных средств",
                "planned_on": str(date.today() + timedelta(days=5)),
            },
            headers=headers,
        )
        assert created.status_code == 201
        response = await async_client.patch(
            f"{_API}/drills/{created.json()['id']}",
            json={"outcome": "passed"},
            headers=headers,
        )
        assert response.status_code == 422
        assert "не проведена" in response.text

    async def test_проведение_в_будущем_не_принимается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Протокол задним числом — можно, вперёд — нет."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        today = date.today()
        created = await async_client.post(
            f"{_API}/drills",
            json={
                "kind": "evacuation",
                "title": "Тренировка, офис",
                "planned_on": str(today),
            },
            headers=headers,
        )
        response = await async_client.patch(
            f"{_API}/drills/{created.json()['id']}",
            json={
                "held_on": str(today + timedelta(days=1)),
                "outcome": "passed",
            },
            headers=headers,
        )
        assert response.status_code == 422
        assert "будущем" in response.text


class TestГотовностьКПроверке:
    async def test_просроченный_план_виден_в_сводке(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Срок прошёл, факта нет → сводка МЧС называет это просрочкой."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        today = date.today()

        before = (await async_client.get(f"{_API}/readiness", headers=headers)).json()

        created = await async_client.post(
            f"{_API}/drills",
            json={
                "kind": "evacuation",
                "title": "Полугодовая тренировка",
                "planned_on": str(today - timedelta(days=10)),
            },
            headers=headers,
        )
        assert created.status_code == 201
        assert created.json()["status"] == "overdue"

        after = (await async_client.get(f"{_API}/readiness", headers=headers)).json()
        assert after["overdue_drills"] == before["overdue_drills"] + 1

        # провели с опозданием → из просрочки уходит, дата попадает в «последняя»
        patched = await async_client.patch(
            f"{_API}/drills/{created.json()['id']}",
            json={"held_on": str(today), "outcome": "passed"},
            headers=headers,
        )
        assert patched.status_code == 200, patched.text
        closed = (await async_client.get(f"{_API}/readiness", headers=headers)).json()
        assert closed["overdue_drills"] == before["overdue_drills"]
        assert closed["last_drill_on"] == str(today)

    async def test_запланированная_вперёд_просрочкой_не_считается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        before = (await async_client.get(f"{_API}/readiness", headers=headers)).json()
        await async_client.post(
            f"{_API}/drills",
            json={
                "kind": "joint",
                "title": "Совместное учение",
                "planned_on": str(date.today() + timedelta(days=30)),
            },
            headers=headers,
        )
        after = (await async_client.get(f"{_API}/readiness", headers=headers)).json()
        assert after["overdue_drills"] == before["overdue_drills"]
        assert after["planned_drills"] == before["planned_drills"] + 1

    async def test_интервал_полгода_не_выдаётся_за_нарушение(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Граница: применимость нормы ППР из данных не следует.

        Тренировка была год назад, новых планов нет — сводка сообщает ДАТУ и
        сколько дней прошло, но НЕ объявляет нарушение: требование «раз в
        полгода» относится к объектам с массовым пребыванием людей, а признака
        массового пребывания у площадки нет. Сторож против соблазна «дописать
        просрочку по интервалу» в следующей волне.
        """

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        today = date.today()
        created = await async_client.post(
            f"{_API}/drills",
            json={
                "kind": "evacuation",
                "title": "Прошлогодняя тренировка",
                "planned_on": str(today - timedelta(days=365)),
            },
            headers=headers,
        )
        await async_client.patch(
            f"{_API}/drills/{created.json()['id']}",
            json={"held_on": str(today - timedelta(days=365)), "outcome": "passed"},
            headers=headers,
        )
        body = (await async_client.get(f"{_API}/readiness", headers=headers)).json()
        assert body["overdue_drills"] == 0
        assert body["last_drill_on"] == str(today - timedelta(days=365))
        assert body["days_since_last_drill"] == 365


class TestИзоляцияАрендатора:
    async def test_чужая_площадка_не_подтверждается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        response = await async_client.post(
            f"{_API}/drills",
            json={
                "kind": "evacuation",
                "title": "Тренировка",
                "planned_on": str(date.today()),
                "site_id": "no-such-site",
            },
            headers=headers,
        )
        assert response.status_code == 422
        assert "Площадка не найдена" in response.text

    async def test_чужая_тренировка_не_читается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        response = await async_client.patch(
            f"{_API}/drills/does-not-exist",
            json={"findings": "правка"},
            headers=headers,
        )
        assert response.status_code == 404


class TestСловариТренировокНаФронте:
    """Срез-104: вид и результат тренировки выбирают в форме из копий словарей.

    Свободная строка сделала бы требуемый разд. 54.1 «анализ» невозможным —
    поэтому оба словаря закрыты, а список формы строится из
    ``FIRE_DRILL_KIND_TITLES`` / ``FIRE_DRILL_OUTCOME_TITLES``
    в ``api/fireSafety.ts``.
    """

    @staticmethod
    def _front_map(name: str) -> dict[str, str]:
        text = _FRONTEND_FIRE_API.read_text(encoding="utf-8")
        block = re.search(
            rf"{name}:\s*Record<[^>]+>\s*=\s*\{{(.*?)\n\}}", text, re.S
        )
        assert block is not None, f"не нашёлся map {name}"
        pairs = re.findall(
            r'([a-z_]+):\s*\n?\s*"([^"]+)"', block.group(1), re.M
        )
        return dict(pairs)

    def test_виды_тренировок_на_фронте_совпадают_с_бэкендом(self) -> None:
        front = self._front_map("FIRE_DRILL_KIND_TITLES")
        assert front == FIRE_DRILL_KINDS, sorted(front.items() ^ FIRE_DRILL_KINDS.items())

    def test_результаты_на_фронте_совпадают_с_бэкендом(self) -> None:
        front = self._front_map("FIRE_DRILL_OUTCOME_TITLES")
        assert front == FIRE_DRILL_OUTCOMES, sorted(
            front.items() ^ FIRE_DRILL_OUTCOMES.items()
        )

