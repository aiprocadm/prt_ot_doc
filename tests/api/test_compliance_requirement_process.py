"""Сторож: «процесс» требования — из словаря, а не свободной строкой (B.18, срез-196).

ЧТО БЫЛО. У требования реестра НПА три привязки: роль, площадка, процесс. Роль
срез-147 сделал закрытым словарём, площадку — выбором из живых. Процесс остался
СВОБОДНОЙ СТРОКОЙ с подсказкой-жаргоном «обучение, СОУТ, медосмотры…», а строка
матрицы объявляла это границей: «словаря процессов в продукте нет».

ЗАЯВЛЕНИЕ БЫЛО НЕВЕРНЫМ. Словарь есть — дисциплины ТЗ (`core/disciplines.py`),
по которым размечен единый календарь и строятся отчёты руководителю. Подсказка
перечисляла ровно их.

ЧТО ЭТО СТОИЛО — и это главное здесь. Пока процесс был свободной строкой,
требования реестра числились источником БЕЗ дисциплины: «обучение»,
«Обучение» и «обучение по ОТ» были тремя разными процессами. Сроки, следующие
из ЗАКОНА, не попадали ни в один дисциплинарный отчёт: «что у нас по пожарной
безопасности» отвечало про тренировки и огнетушители и молчало про обязанность
из приказа.

ЗАПУСК: ``PYTHONPATH=backend pytest tests/api/test_compliance_requirement_process.py -v``.
"""

from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.core.config import get_settings
from app.core.disciplines import (
    GENERAL_PROCESS,
    PROCESS_TITLES,
    Discipline,
    discipline_of,
    discipline_of_event,
)
from app.models.models import RoleEnum

BASE = "/api/v1/compliance/requirements"
NPA = "/api/v1/npa"
FAR_FUTURE = date(2999, 1, 1)


@pytest.fixture(autouse=True)
def _managing_tenant(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PLATFORM_TENANT_SLUG", "test")
    get_settings.cache_clear()  # type: ignore[attr-defined]
    yield
    get_settings.cache_clear()  # type: ignore[attr-defined]


async def _act(client: AsyncClient, headers: dict[str, str]) -> dict:
    response = await client.post(
        NPA,
        json={
            "code": f"{uuid4().hex[:6]}н",
            "title": "Приказ об обучении",
            "edition": "ред. 2026",
            "valid_from": "2026-01-01",
            "clauses": [{"code": "п. 1", "text": "Обучать ежегодно"}],
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


class TestСловарьПроцессов:
    def test_процессы_это_дисциплины_плюс_общая_охрана_труда(self) -> None:
        """Не выдуманный список: ровно тот словарь, которым размечен календарь."""

        assert set(PROCESS_TITLES) == {d.value for d in Discipline} | {GENERAL_PROCESS}
        assert PROCESS_TITLES["training"] == "Обучение"
        assert PROCESS_TITLES["medical"] == "Медосмотры"

    def test_общая_охрана_труда_не_дисциплина(self) -> None:
        """У неё есть имя, но нет дисциплины, и это ПРАВДА, а не пробел.

        Если бы «общая охрана труда» отображалась в какую-то дисциплину, отчёт
        по этой дисциплине показывал бы чужое.
        """

        assert (
            discipline_of_event("compliance_requirement", {"process_code": GENERAL_PROCESS})
            is None
        )


class TestДисциплинаСрокаТребования:
    """ГЛАВНОЕ СЛЕДСТВИЕ СРЕЗА: срок из закона попадает в свою дисциплину."""

    def test_срок_требования_получил_дисциплину(self) -> None:
        assert (
            discipline_of_event("compliance_requirement", {"process_code": "fire_safety"})
            is Discipline.FIRE_SAFETY
        )

    def test_источник_целиком_по_прежнему_без_дисциплины(self) -> None:
        """Обязанность бывает общей для арендатора — приписывать источнику
        дисциплину целиком было бы враньём. Разметка ПОЗАПИСНАЯ."""

        assert discipline_of("compliance_requirement") is None

    def test_требование_без_процесса_дисциплины_не_получает(self) -> None:
        assert discipline_of_event("compliance_requirement", {"process_code": None}) is None
        assert discipline_of_event("compliance_requirement", {}) is None

    def test_старая_свободная_строка_не_приписывается_к_дисциплине(self) -> None:
        """У требований до среза в поле лежит текст. Угадать по нему дисциплину
        значило бы выдумать данные — тот же отказ, что у видов инструктажа."""

        assert (
            discipline_of_event("compliance_requirement", {"process_code": "обучение по ОТ"})
            is None
        )


@pytest.mark.anyio
async def test_справочник_формы_отдаёт_процессы(
    async_client: AsyncClient, make_auth_headers
) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)
    response = await async_client.get(f"{BASE}/options", headers=headers)
    assert response.status_code == 200, response.text
    processes = response.json()["processes"]
    assert {item["code"] for item in processes} == set(PROCESS_TITLES)
    # Подписи — словами: выбирает человек, а не машина.
    assert {"code": "training", "label": "Обучение"} in processes


@pytest.mark.anyio
async def test_выдуманный_процесс_отвергается_на_записи(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """Иначе «к чему относится» снова стало бы свободной строкой, по которой
    ничего не отобрать — ровно то, что срез-147 закрыл для роли."""

    headers = await make_auth_headers(RoleEnum.ADMIN)
    act = await _act(async_client, headers)
    response = await async_client.post(
        BASE,
        json={
            "code": f"ОТ-{uuid4().hex[:8]}",
            "title": "Проводить обучение",
            "severity": "high",
            "npa_id": act["id"],
            "process_code": "обучение по ОТ",
            "next_due_at": FAR_FUTURE.isoformat(),
        },
        headers=headers,
    )
    assert response.status_code == 422, response.text
    assert "справочник" in response.text.lower() or "выберите" in response.text.lower()


@pytest.mark.anyio
async def test_процесс_из_словаря_принимается_и_возвращается_словами(
    async_client: AsyncClient, make_auth_headers
) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)
    act = await _act(async_client, headers)
    created = await async_client.post(
        BASE,
        json={
            "code": f"ОТ-{uuid4().hex[:8]}",
            "title": "Проверять огнетушители",
            "severity": "high",
            "npa_id": act["id"],
            "process_code": "fire_safety",
            "next_due_at": FAR_FUTURE.isoformat(),
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["process_code"] == "fire_safety"
    assert body["process_label"] == "Пожарная безопасность"


@pytest.mark.anyio
async def test_правка_тоже_проверяет_процесс(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """Проверка только на создании оставила бы вторую дверь открытой."""

    headers = await make_auth_headers(RoleEnum.ADMIN)
    act = await _act(async_client, headers)
    created = await async_client.post(
        BASE,
        json={
            "code": f"ОТ-{uuid4().hex[:8]}",
            "title": "Требование",
            "severity": "low",
            "npa_id": act["id"],
            "next_due_at": FAR_FUTURE.isoformat(),
        },
        headers=headers,
    )
    requirement_id = created.json()["id"]
    bad = await async_client.patch(
        f"{BASE}/{requirement_id}", json={"process_code": "выдумка"}, headers=headers
    )
    assert bad.status_code == 422, bad.text
    good = await async_client.patch(
        f"{BASE}/{requirement_id}", json={"process_code": "ecology"}, headers=headers
    )
    assert good.status_code == 200, good.text
    assert good.json()["process_label"] == "Экология"


@pytest.mark.anyio
async def test_старое_значение_показывается_как_есть_а_не_стирается(
    async_client: AsyncClient, make_auth_headers, sessionmaker
) -> None:
    """Требования, заведённые до среза, нельзя молча обнулять.

    Свободный текст — единственное, что человек про этот процесс написал;
    стереть его при чтении значило бы потерять данные ради красоты словаря.
    """

    from sqlalchemy import select

    from app.models.compliance_requirements import ComplianceRequirement

    headers = await make_auth_headers(RoleEnum.ADMIN)
    act = await _act(async_client, headers)
    code = f"ОТ-{uuid4().hex[:8]}"
    created = await async_client.post(
        BASE,
        json={
            "code": code,
            "title": "Старое требование",
            "severity": "low",
            "npa_id": act["id"],
            "next_due_at": FAR_FUTURE.isoformat(),
        },
        headers=headers,
    )
    requirement_id = created.json()["id"]

    # Пишем свободный текст мимо ручки — так выглядят строки до среза-196.
    async with sessionmaker() as session:
        row = await session.scalar(
            select(ComplianceRequirement).where(ComplianceRequirement.id == requirement_id)
        )
        row.process_code = "обучение по ОТ"
        await session.commit()

    read = await async_client.get(f"{BASE}/{requirement_id}", headers=headers)
    assert read.status_code == 200, read.text
    body = read.json()
    assert body["process_code"] == "обучение по ОТ"
    assert body["process_label"] == "обучение по ОТ"
