"""Контур ПромБез срез-5 (Доп. №1 разд. 54.2): производственный контроль.

СВЕРКА, С КОТОРОЙ НАЧАЛСЯ СРЕЗ. ТЗ требует «производственный контроль: план ПК,
мероприятия, ответственные, отчётность в надзор». В коде не было НИЧЕГО:
поиск по ``production_control`` давал единственное попадание — подпись поля
«Производственный контроль» в комплекте документов по отходам, то есть строку
на бумаге, а не сущность.

Что заводится и почему именно так:

* **план ПК — своя сущность**: это годовой документ организации,
  эксплуатирующей ОПО, со своим утверждением и ответственным за осуществление
  производственного контроля; в ядре такого нет;
* **мероприятия плана — тоже свои**, но с разделами из ЗАКРЫТОГО словаря:
  свободная строка снова сделала бы отчётность непересчитываемой;
* **ответственные и сроки НЕ дублируют ядро задач**: план — это документ, а не
  очередь поручений; выполнение мероприятия отмечается в самом плане, потому
  что именно план предъявляется надзору.

ГРАНИЦА: платформа сообщает ФАКТ «плана на текущий год нет», но не объявляет
это нарушением — обязанность организовать производственный контроль зависит от
того, эксплуатирует ли организация ОПО, и полноту этих сведений в системе
определяет специалист. Тот же довод, что у интервала тренировок и требования
ЭПБ.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select

from app.models.feature import Feature, FeatureEnablement
from app.models.industrial_safety import (
    PC_MEASURE_SECTIONS,
    PC_MEASURE_STATUS_TITLES,
    PC_MEASURE_WRITABLE_STATUSES,
    PC_PLAN_STATUSES,
)
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


async def _plan(async_client, headers, year: int | None = None) -> str:
    response = await async_client.post(
        f"{_API}/pc-plans",
        json={
            "year": year or date.today().year,
            "title": "План производственного контроля",
            "responsible": "Главный инженер Петров",
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


class TestПланПК:
    async def test_без_выдачи_модуль_невидим(self, async_client, make_auth_headers) -> None:
        headers = await make_auth_headers()
        response = await async_client.get(f"{_API}/pc-plans", headers=headers)
        assert response.status_code == 404

    async def test_план_заводится_и_утверждается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        plan_id = await _plan(async_client, headers)

        listed = await async_client.get(f"{_API}/pc-plans", headers=headers)
        row = next(r for r in listed.json()["items"] if r["id"] == plan_id)
        assert row["status"] == "draft"
        assert row["status_label"] == "Проект"

        approved = await async_client.patch(
            f"{_API}/pc-plans/{plan_id}",
            json={"status": "approved", "approved_on": str(date.today())},
            headers=headers,
        )
        assert approved.status_code == 200, approved.text
        assert approved.json()["status_label"] == "Утверждён"

    async def test_два_плана_на_один_год_не_заводятся(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """План ПК — годовой документ: второй на тот же год это дубль.

        Дубль сделал бы бессмысленным сам вопрос «есть ли план на 2026 год».
        """

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        year = date.today().year
        await _plan(async_client, headers, year)
        response = await async_client.post(
            f"{_API}/pc-plans",
            json={"year": year, "title": "Второй план"},
            headers=headers,
        )
        assert response.status_code == 422
        assert "уже заведён" in response.text

    async def test_неизвестное_состояние_плана_отвергается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        plan_id = await _plan(async_client, headers)
        response = await async_client.patch(
            f"{_API}/pc-plans/{plan_id}",
            json={"status": "подписан"},
            headers=headers,
        )
        assert response.status_code == 422
        assert "Неизвестное состояние" in response.text


class TestМероприятияПлана:
    async def test_мероприятие_заводится_с_разделом_словами(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        plan_id = await _plan(async_client, headers)
        response = await async_client.post(
            f"{_API}/pc-measures",
            json={
                "plan_id": plan_id,
                "section": "inspections",
                "title": "Обследование технического состояния котельной",
                "due_on": str(date.today() + timedelta(days=60)),
                "responsible": "Механик Сидоров",
            },
            headers=headers,
        )
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["section_label"] == "Обследования и проверки состояния ОПО"
        assert body["status"] == "planned"
        assert body["status_label"] == "Запланировано"

    async def test_неизвестный_раздел_отвергается_словами(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """Свободная строка раздела сделала бы отчётность непересчитываемой."""

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        plan_id = await _plan(async_client, headers)
        response = await async_client.post(
            f"{_API}/pc-measures",
            json={
                "plan_id": plan_id,
                "section": "разное",
                "title": "Что-то",
                "due_on": str(date.today()),
            },
            headers=headers,
        )
        assert response.status_code == 422
        assert "Неизвестный раздел" in response.text

    async def test_мероприятие_без_плана_не_принимается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        response = await async_client.post(
            f"{_API}/pc-measures",
            json={
                "plan_id": "no-such-plan",
                "section": "training",
                "title": "Обучение",
                "due_on": str(date.today()),
            },
            headers=headers,
        )
        assert response.status_code == 422
        assert "План не найден" in response.text

    async def test_выполнение_требует_даты(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """«Выполнено» без даты выполнения — отметка без свидетельства.

        Именно дата предъявляется надзору как доказательство исполнения плана.
        """

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        plan_id = await _plan(async_client, headers)
        created = await async_client.post(
            f"{_API}/pc-measures",
            json={
                "plan_id": plan_id,
                "section": "epb",
                "title": "Экспертиза сосуда Р-1",
                "due_on": str(date.today()),
            },
            headers=headers,
        )
        response = await async_client.patch(
            f"{_API}/pc-measures/{created.json()['id']}",
            json={"status": "done"},
            headers=headers,
        )
        assert response.status_code == 422
        assert "дата выполнения" in response.text

    async def test_выполнение_в_будущем_не_принимается(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        plan_id = await _plan(async_client, headers)
        created = await async_client.post(
            f"{_API}/pc-measures",
            json={
                "plan_id": plan_id,
                "section": "emergency",
                "title": "Учебная тревога",
                "due_on": str(date.today()),
            },
            headers=headers,
        )
        response = await async_client.patch(
            f"{_API}/pc-measures/{created.json()['id']}",
            json={"status": "done", "completed_on": str(date.today() + timedelta(days=1))},
            headers=headers,
        )
        assert response.status_code == 422
        assert "будущем" in response.text

    async def test_просроченное_мероприятие_названо_просроченным(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        plan_id = await _plan(async_client, headers)
        created = await async_client.post(
            f"{_API}/pc-measures",
            json={
                "plan_id": plan_id,
                "section": "violations",
                "title": "Устранение замечаний прошлой проверки",
                "due_on": str(date.today() - timedelta(days=5)),
            },
            headers=headers,
        )
        assert created.json()["status_label"] == "Просрочено"

        done = await async_client.patch(
            f"{_API}/pc-measures/{created.json()['id']}",
            json={
                "status": "done",
                "completed_on": str(date.today()),
                "result": "Замечания устранены, акт №12",
            },
            headers=headers,
        )
        assert done.status_code == 200, done.text
        assert done.json()["status_label"] == "Выполнено"


class TestСводкаПроизводственногоКонтроля:
    async def test_наличие_плана_и_просрочки_в_сводке(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        before = (await async_client.get(f"{_API}/readiness", headers=headers)).json()
        assert before["current_year_plan_exists"] is False

        plan_id = await _plan(async_client, headers)
        await async_client.post(
            f"{_API}/pc-measures",
            json={
                "plan_id": plan_id,
                "section": "reporting",
                "title": "Отчёт в Ростехнадзор",
                "due_on": str(date.today() - timedelta(days=3)),
            },
            headers=headers,
        )

        after = (await async_client.get(f"{_API}/readiness", headers=headers)).json()
        assert after["current_year_plan_exists"] is True
        assert after["pc_measures_overdue"] == before["pc_measures_overdue"] + 1

    async def test_отсутствие_плана_не_объявляется_нарушением(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        """ГРАНИЦА: обязанность вести ПК зависит от того, эксплуатирует ли
        организация ОПО, и полноту сведений определяет специалист.

        Сторож против соблазна дописать в сводку «нарушение: плана ПК нет» в
        следующей волне: отдаём факт наличия, а не приговор.
        """

        headers = await make_auth_headers()
        await _grant(sessionmaker)
        body = (await async_client.get(f"{_API}/readiness", headers=headers)).json()
        assert body["current_year_plan_exists"] is False
        assert "pc_violation" not in body
        assert "pc_required" not in body


class TestИзоляцияАрендатора:
    async def test_чужой_план_не_правится(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        response = await async_client.patch(
            f"{_API}/pc-plans/does-not-exist",
            json={"title": "Подмена"},
            headers=headers,
        )
        assert response.status_code == 404

    async def test_чужое_мероприятие_не_правится(
        self, async_client, make_auth_headers, sessionmaker
    ) -> None:
        headers = await make_auth_headers()
        await _grant(sessionmaker)
        response = await async_client.patch(
            f"{_API}/pc-measures/does-not-exist",
            json={"title": "Подмена"},
            headers=headers,
        )
        assert response.status_code == 404


class TestСловариПкНаФронте:
    """Срез-106: план и мероприятия ПК заводят с экрана.

    Главное здесь — список состояний мероприятия: в форме только те, что
    МОЖНО выставить руками. «Просрочено» вычисляется по сроку, и появись оно в
    списке — человек «ставил» бы просрочку сам, а сервер отвечал бы 422.
    """

    def test_состояния_плана_на_фронте_совпадают_с_бэкендом(self) -> None:
        front = _front_map("PC_PLAN_STATUS_TITLES")
        assert front == PC_PLAN_STATUSES, sorted(front.items() ^ PC_PLAN_STATUSES.items())

    def test_разделы_плана_на_фронте_совпадают_с_бэкендом(self) -> None:
        front = _front_map("PC_MEASURE_SECTION_TITLES")
        assert front == PC_MEASURE_SECTIONS, sorted(front.items() ^ PC_MEASURE_SECTIONS.items())

    def test_в_форме_только_записываемые_состояния_мероприятия(self) -> None:
        front = _front_map("PC_MEASURE_WRITABLE_STATUS_TITLES")
        assert set(front) == set(PC_MEASURE_WRITABLE_STATUSES), sorted(
            set(front) ^ set(PC_MEASURE_WRITABLE_STATUSES)
        )
        assert "overdue" not in front
        for code, title in front.items():
            assert title == PC_MEASURE_STATUS_TITLES[code], code
