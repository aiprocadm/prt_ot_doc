"""Сторож: у редакции акта есть явный статус (B.18 разд. 19.4, срез-198).

ЧТО БЫЛО. Список редакций показывал код, название и диапазон дат — и НИЧЕГО про
то, какая из них действует. Будущая редакция выглядела ровно так же, как
действующая.

Это не косметика. Владелец платформы заводит редакцию ЗАРАНЕЕ — так и задумано
(«арендаторы узнают о ней в день вступления в силу»). Пока она не помечена,
специалист по охране труда видит её в списке и может начать исполнять новые
правила РАНЬШЕ СРОКА. В продукте про законы это не мелочь.

ГЛАВНАЯ ТОНКОСТЬ, найденная при написании кода и закреплённая отдельной
проверкой: «действующая» и «выбранная для предпросмотра» — РАЗНЫЕ вещи. Экран
умеет считать влияние по выбранной редакции, в том числе будущей. Если статус
считать по выбранной, будущая редакция в режиме предпросмотра пометится
«Действует» — то есть ровно тот вред, от которого статус и защищает.

ЗАПУСК: ``PYTHONPATH=backend pytest tests/api/test_npa_revision_status.py -v``.
"""

from __future__ import annotations

from datetime import date, timedelta
from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.core.config import get_settings
from app.domains.npa.impact import (
    REVISION_ACTIVE,
    REVISION_EXPIRED,
    REVISION_STATUS_TITLES,
    REVISION_SUPERSEDED,
    REVISION_UPCOMING,
    revision_status,
)
from app.models.models import RoleEnum
from app.models.npa import NpaRevision

NPA = "/api/v1/npa"
TODAY = date(2026, 6, 15)


@pytest.fixture(autouse=True)
def _managing_tenant(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PLATFORM_TENANT_SLUG", "test")
    get_settings.cache_clear()  # type: ignore[attr-defined]
    yield
    get_settings.cache_clear()  # type: ignore[attr-defined]


def _revision(rid: str, *, start: date | None, end: date | None) -> NpaRevision:
    return NpaRevision(
        id=rid, act_id="a-1", revision_code=rid, title=rid, effective_from=start, effective_to=end
    )


class TestСостояниеРедакции:
    def test_действующая_помечена(self) -> None:
        active = _revision("now", start=date(2026, 1, 1), end=None)
        assert revision_status(active, active=active, today=TODAY) == REVISION_ACTIVE

    def test_будущая_названа_словами(self) -> None:
        """ГЛАВНОЕ: иначе человек начнёт исполнять новые правила раньше срока."""

        active = _revision("now", start=date(2026, 1, 1), end=None)
        future = _revision("next", start=date(2026, 9, 1), end=None)
        assert revision_status(future, active=active, today=TODAY) == REVISION_UPCOMING
        assert REVISION_STATUS_TITLES[REVISION_UPCOMING] == "Ещё не вступила в силу"

    def test_прошедшая_названа_словами(self) -> None:
        active = _revision("now", start=date(2026, 1, 1), end=None)
        old = _revision("old", start=date(2024, 1, 1), end=date(2025, 12, 31))
        assert revision_status(old, active=active, today=TODAY) == REVISION_EXPIRED

    def test_перекрытая_не_выдаётся_за_действующую(self) -> None:
        """Диапазоны могут перекрыться, и «сегодня» покроет несколько.

        Система работает ровно по одной. Показать вторую как действующую значило
        бы дать два разных ответа на вопрос «по чему мы сейчас живём».
        """

        active = _revision("now", start=date(2026, 5, 1), end=None)
        overlapping = _revision("also", start=date(2026, 1, 1), end=date(2026, 12, 31))
        assert revision_status(overlapping, active=active, today=TODAY) == REVISION_SUPERSEDED

    def test_без_действующей_редакции_будущая_остаётся_будущей(self) -> None:
        """Акт, у которого все редакции впереди: «действующей» нет, и
        приписывать её кому-то нельзя."""

        future = _revision("next", start=date(2026, 9, 1), end=None)
        assert revision_status(future, active=None, today=TODAY) == REVISION_UPCOMING

    def test_у_каждого_состояния_есть_подпись_словами(self) -> None:
        for code in (REVISION_ACTIVE, REVISION_UPCOMING, REVISION_EXPIRED, REVISION_SUPERSEDED):
            assert REVISION_STATUS_TITLES[code].strip()
            assert REVISION_STATUS_TITLES[code] != code


@pytest.mark.anyio
async def test_ручка_отдаёт_статус_каждой_редакции(
    async_client: AsyncClient, make_auth_headers
) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)
    act = await async_client.post(
        NPA,
        json={
            "code": f"{uuid4().hex[:6]}н",
            "title": "Приказ",
            "edition": "ред. 2026",
            "valid_from": "2026-01-01",
            "clauses": [{"code": "п. 1", "text": "Текст"}],
        },
        headers=headers,
    )
    assert act.status_code == 201, act.text
    act_id = act.json()["id"]

    today = date.today()
    now = await async_client.post(
        f"{NPA}/{act_id}/revisions",
        json={
            "revision_code": "rev-now",
            "title": "Действующая",
            "effective_from": (today - timedelta(days=30)).isoformat(),
        },
        headers=headers,
    )
    assert now.status_code == 201, now.text
    later = await async_client.post(
        f"{NPA}/{act_id}/revisions",
        json={
            "revision_code": "rev-next",
            "title": "Будущая",
            "effective_from": (today + timedelta(days=60)).isoformat(),
        },
        headers=headers,
    )
    assert later.status_code == 201, later.text

    detail = await async_client.get(f"{NPA}/{act_id}", headers=headers)
    by_code = {r["revision_code"]: r for r in detail.json()["revisions"]}
    assert by_code["rev-now"]["status"] == REVISION_ACTIVE
    assert by_code["rev-next"]["status"] == REVISION_UPCOMING
    # Подпись словами приходит с сервера: витрина не должна знать словарь.
    assert by_code["rev-next"]["status_title"] == "Ещё не вступила в силу"


@pytest.mark.anyio
async def test_предпросмотр_будущей_редакции_не_делает_её_действующей(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """ГЛАВНАЯ ТОНКОСТЬ СРЕЗА.

    Экран умеет считать влияние по ВЫБРАННОЙ редакции, в том числе будущей.
    Если статус считать по выбранной, будущая редакция в предпросмотре
    пометится «Действует» — ровно тот вред, от которого статус и защищает.
    """

    headers = await make_auth_headers(RoleEnum.ADMIN)
    act = await async_client.post(
        NPA,
        json={
            "code": f"{uuid4().hex[:6]}н",
            "title": "Приказ",
            "edition": "ред. 2026",
            "valid_from": "2026-01-01",
            "clauses": [{"code": "п. 1", "text": "Текст"}],
        },
        headers=headers,
    )
    act_id = act.json()["id"]
    today = date.today()
    await async_client.post(
        f"{NPA}/{act_id}/revisions",
        json={
            "revision_code": "rev-now",
            "title": "Действующая",
            "effective_from": (today - timedelta(days=30)).isoformat(),
        },
        headers=headers,
    )
    future = await async_client.post(
        f"{NPA}/{act_id}/revisions",
        json={
            "revision_code": "rev-next",
            "title": "Будущая",
            "effective_from": (today + timedelta(days=60)).isoformat(),
        },
        headers=headers,
    )
    future_id = future.json()["id"]

    preview = await async_client.get(
        f"{NPA}/{act_id}", params={"revision_id": future_id}, headers=headers
    )
    by_code = {r["revision_code"]: r for r in preview.json()["revisions"]}
    assert by_code["rev-next"]["status"] == REVISION_UPCOMING, (
        "будущая редакция помечена действующей в предпросмотре — человек начнёт "
        "исполнять её раньше срока"
    )
    assert by_code["rev-now"]["status"] == REVISION_ACTIVE
