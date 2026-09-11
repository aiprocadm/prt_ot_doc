"""Срез-144 (B.18 разд. 19.4): связь с НПА помнит, по какой редакции её сверяли.

До среза новая редакция акта уходила в общий реестр молча: владелец платформы
заводил её ``POST /npa/{id}/revisions``, а арендатор узнавал об этом, только
если сам открыл акт и нажал «Создать задачи». Ни уведомления, ни контроля,
что документы после смены редакции кто-то пересмотрел, не было — цепочка
«уведомить → задачи → контроль» из разд. 19.4 обрывалась на первом звене.

Теперь ``NPABinding.reviewed_revision_id`` — редакция, по которой связь сверяли
в последний раз. Ставится при создании связи (действующая редакция) и кнопкой
«Пересмотрено». Пока действует та же редакция — связь актуальна; вступила
новая — связь «не пересмотрена».

Что закреплено:
  * новая связь берёт действующую редакцию и не «не пересмотрена»;
  * вступила новая редакция — связь ``stale``, у акта ``stale_bindings=1``,
    в Центре внимания запись ``npa_revision`` и совет пересмотреть;
  * задачи актуализации считаются по непересмотренным связям, а не по всем;
  * «Пересмотрено» — 200, связь снова актуальна, запись из Центра ушла;
  * редакция с датой вступления в будущем ничего не меняет (черновик →
    публикация по дате);
  * акт без редакций: связь не бывает «не пересмотренной», задачи — по всем
    связям, как раньше;
  * чужая связь — 404, рядовая роль — 403; работник записей НПА не видит.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.core.config import get_settings
from app.models.models import RoleEnum

BASE = "/api/v1/npa"
ATTENTION = "/api/v1/workspace/attention"


@pytest.fixture(autouse=True)
def _managing_tenant(monkeypatch: pytest.MonkeyPatch):
    """Акты и редакции заводит владелец платформы — арендатор «test»."""

    monkeypatch.setenv("PLATFORM_TENANT_SLUG", "test")
    get_settings.cache_clear()  # type: ignore[attr-defined]
    yield
    get_settings.cache_clear()  # type: ignore[attr-defined]


async def _create_act(client: AsyncClient, headers: dict[str, str]) -> dict:
    response = await client.post(
        BASE,
        json={
            "code": f"{uuid4().hex[:6]}н",
            "title": "Приказ об обучении по охране труда",
            "edition": "ред. 2026",
            "valid_from": "2026-01-01",
            "clauses": [],
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _add_revision(
    client: AsyncClient, headers: dict[str, str], act_id: str, code: str, effective_from: str
) -> dict:
    # Даты — в прошлом или далёком будущем нарочно: «сегодня» у продукта по
    # UTC, у процесса тестов — по Москве, и вечером это разные дни (срез-140).
    response = await client.post(
        f"{BASE}/{act_id}/revisions",
        json={
            "revision_code": code,
            "title": f"Редакция {code}",
            "effective_from": effective_from,
            "effective_to": None,
            "change_summary": "Обновлены программы обучения",
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _seed_document(sessionmaker, data_factory) -> str:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        template = await data_factory.create_template(
            tenant=tenant, name=f"Инструкция {uuid4().hex[:4]}", session=session
        )
        company = await data_factory.create_company(
            tenant=tenant, name=f"ООО Ромашка {uuid4().hex[:4]}", session=session
        )
        document, _ = await data_factory.create_document(
            tenant=tenant, template=template, company=company, session=session
        )
        await session.commit()
        return document.id


async def _bind(
    client: AsyncClient, headers: dict[str, str], act_id: str, document_id: str
) -> dict:
    response = await client.post(
        f"{BASE}/{act_id}/bindings",
        json={"entity_type": "document", "entity_id": document_id, "ref": "п. 4"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _npa_items(attention: dict, act_id: str) -> list[dict]:
    return [
        item
        for item in attention["items"]
        if item["item_type"] == "npa_revision" and item["entity_id"] == act_id
    ]


@pytest.mark.anyio
async def test_новая_редакция_делает_связь_непересмотренной_а_кнопка_возвращает(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory
) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)
    act = await _create_act(async_client, headers)
    first = await _add_revision(async_client, headers, act["id"], "ред-1", "2026-01-01")
    document_id = await _seed_document(sessionmaker, data_factory)

    binding = await _bind(async_client, headers, act["id"], document_id)
    assert binding["reviewed_revision_id"] == first["id"]
    assert binding["reviewed_revision_code"] == "ред-1"
    assert binding["stale"] is False

    detail = (await async_client.get(f"{BASE}/{act['id']}", headers=headers)).json()
    assert detail["stale_bindings"] == 0
    assert detail["binding_items"][0]["stale"] is False
    # Пока связь актуальна, актуализировать нечего.
    assert detail["tasks_to_create"] == []
    attention = (await async_client.get(ATTENTION, headers=headers)).json()
    assert _npa_items(attention, act["id"]) == []
    assert attention["summary"]["stale_npa_bindings"] == 0

    second = await _add_revision(async_client, headers, act["id"], "ред-2", "2026-06-01")

    detail = (await async_client.get(f"{BASE}/{act['id']}", headers=headers)).json()
    assert detail["active_revision_id"] == second["id"]
    assert detail["stale_bindings"] == 1
    item = detail["binding_items"][0]
    assert item["stale"] is True
    assert item["reviewed_revision_code"] == "ред-1"
    assert detail["tasks_to_create"] == [
        {
            "code": "npa-update-documents",
            "title": "Актуализировать зависимости НПА: documents",
            "count": 1,
        }
    ]
    attention = (await async_client.get(ATTENTION, headers=headers)).json()
    (npa_item,) = _npa_items(attention, act["id"])
    assert npa_item["severity"] == "high"
    assert npa_item["status"] == "stale"
    assert npa_item["entity_type"] == "npa"
    assert npa_item["reason"] == "Реестр НПА обновился"
    assert f"НПА {act['code']}: редакция ред-2" in npa_item["title"]
    assert "не пересмотрено связей: 1 из 1" in npa_item["title"]
    assert attention["summary"]["stale_npa_bindings"] == 1
    assert "Пересмотрите документы по обновлённым НПА" in attention["recommendations"]

    reviewed = await async_client.post(
        f"{BASE}/{act['id']}/bindings/{binding['id']}/review", headers=headers
    )
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["reviewed_revision_id"] == second["id"]
    assert reviewed.json()["reviewed_revision_code"] == "ред-2"
    assert reviewed.json()["stale"] is False

    detail = (await async_client.get(f"{BASE}/{act['id']}", headers=headers)).json()
    assert detail["stale_bindings"] == 0
    assert detail["tasks_to_create"] == []
    attention = (await async_client.get(ATTENTION, headers=headers)).json()
    assert _npa_items(attention, act["id"]) == []
    assert attention["summary"]["stale_npa_bindings"] == 0
    assert "Пересмотрите документы по обновлённым НПА" not in attention["recommendations"]

    # Повторное «Пересмотрено» безвредно.
    again = await async_client.post(
        f"{BASE}/{act['id']}/bindings/{binding['id']}/review", headers=headers
    )
    assert again.status_code == 200
    assert again.json()["reviewed_revision_id"] == second["id"]


@pytest.mark.anyio
async def test_будущая_редакция_ничего_не_меняет_до_дня_вступления(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory
) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)
    act = await _create_act(async_client, headers)
    current = await _add_revision(async_client, headers, act["id"], "ред-1", "2026-01-01")
    binding = await _bind(
        async_client, headers, act["id"], await _seed_document(sessionmaker, data_factory)
    )
    assert binding["reviewed_revision_id"] == current["id"]

    await _add_revision(async_client, headers, act["id"], "ред-2999", "2999-01-01")

    detail = (await async_client.get(f"{BASE}/{act['id']}", headers=headers)).json()
    assert detail["active_revision_id"] == current["id"]
    assert detail["stale_bindings"] == 0
    assert detail["tasks_to_create"] == []
    attention = (await async_client.get(ATTENTION, headers=headers)).json()
    assert _npa_items(attention, act["id"]) == []


@pytest.mark.anyio
async def test_акт_без_редакций_считает_задачи_по_всем_связям_как_раньше(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory
) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)
    act = await _create_act(async_client, headers)
    binding = await _bind(
        async_client, headers, act["id"], await _seed_document(sessionmaker, data_factory)
    )
    assert binding["reviewed_revision_id"] is None
    assert binding["stale"] is False

    detail = (await async_client.get(f"{BASE}/{act['id']}", headers=headers)).json()
    assert detail["stale_bindings"] == 0
    assert [t["count"] for t in detail["tasks_to_create"]] == [1]
    attention = (await async_client.get(ATTENTION, headers=headers)).json()
    assert _npa_items(attention, act["id"]) == []

    # «Пересмотрено» без редакций — тоже 200: сверять не с чем, связь актуальна.
    reviewed = await async_client.post(
        f"{BASE}/{act['id']}/bindings/{binding['id']}/review", headers=headers
    )
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["reviewed_revision_id"] is None


@pytest.mark.anyio
async def test_чужую_связь_не_пересмотреть_а_рядовой_роли_нельзя_вовсе(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory
) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)
    act = await _create_act(async_client, headers)
    await _add_revision(async_client, headers, act["id"], "ред-1", "2026-01-01")
    binding = await _bind(
        async_client, headers, act["id"], await _seed_document(sessionmaker, data_factory)
    )
    await _add_revision(async_client, headers, act["id"], "ред-2", "2026-06-01")

    worker = await make_auth_headers(RoleEnum.WORKER)
    forbidden = await async_client.post(
        f"{BASE}/{act['id']}/bindings/{binding['id']}/review", headers=worker
    )
    assert forbidden.status_code == 403, forbidden.text
    # Работник свои документы по НПА не пересматривает — и записей о них не видит.
    attention = (await async_client.get(ATTENTION, headers=worker)).json()
    assert _npa_items(attention, act["id"]) == []
    assert attention["summary"]["stale_npa_bindings"] == 0

    async with sessionmaker() as session:
        await data_factory.ensure_tenant(slug="outsider", session=session)
        await session.commit()
    outsider = await make_auth_headers(
        RoleEnum.ADMIN, tenant="outsider", email="admin-outsider-npa-review@example.com"
    )
    missing = await async_client.post(
        f"{BASE}/{act['id']}/bindings/{binding['id']}/review", headers=outsider
    )
    assert missing.status_code == 404, missing.text
    # Связь осталась непересмотренной: чужой вызов её не тронул.
    detail = (await async_client.get(f"{BASE}/{act['id']}", headers=headers)).json()
    assert detail["stale_bindings"] == 1
