"""Сторож: сводка влияния перестала врать нулями (B.18 разд. 19.3, срез-197).

ЧТО БЫЛО. Оценка влияния акта перечисляла восемь категорий. Пять из них
(риски, чек-листы, маршруты, роли, площадки) читались из свободного поля
``context`` у связи — а ручка создания связи ставила этот контекст ЖЁСТКО
ПУСТЫМ. Читатель был, писателя не было.

Экран нули не показывает, поэтому эти строки просто НИКОГДА не появлялись:
человек видел перечень затронутого без «Рисков» и «Маршрутов» и читал это как
«этот закон их не задевает». Отсутствие строки — такое же утверждение, как ноль,
и такое же ложное. «Связей нет» и «мы такие связи не записываем» — разные вещи.

ЧТО СДЕЛАНО. Роли и площадки — это ОБЛАСТЬ ДЕЙСТВИЯ связи («кого и где
касается»), и оба уже есть закрытым словарём и живым реестром: они стали
записываемыми. Риски, чек-листы и маршруты — самостоятельные сущности со своими
экранами; привязка к ним отдельная работа, и до неё рядом с категорией отдаётся
ПРИЧИНА, которую видно на экране.

ЧЕГО ЗДЕСЬ НЕ СДЕЛАНО И ПОЧЕМУ. Убрать эти категории из сводки было
соблазнительно, но неверно: читатель общий, и связь может прийти импортом или
будущей фичей. Спрятать существующую связь хуже, чем показать ноль.

ЗАПУСК: ``PYTHONPATH=backend pytest tests/api/test_npa_binding_context.py -v``.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.core.config import get_settings
from app.domains.npa.impact import RECORDABLE_CONTEXT, UNRECORDED_IMPACT
from app.models.models import RoleEnum

NPA = "/api/v1/npa"


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


async def _seed(sessionmaker, data_factory) -> tuple[str, str]:
    """Документ и площадка арендатора: связь заводят на них."""

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
        site = await data_factory.create_site(
            tenant=tenant, company=company, name=f"Цех {uuid4().hex[:4]}", session=session
        )
        await session.commit()
        return document.id, site.id


class TestНеведущиесяКатегории:
    def test_риски_чеклисты_маршруты_объявлены_с_причиной(self) -> None:
        """ГЛАВНОЕ: рядом с вечным нулём появилась причина, которую видно."""

        assert set(UNRECORDED_IMPACT) == {"risks", "checklists", "workflows"}
        for category, reason in UNRECORDED_IMPACT.items():
            assert reason.strip(), f"{category} без причины"
            # Причина — словами для человека, а не код и не «нет данных».
            assert "не ведётся" in reason

    def test_записываемое_и_неведущееся_не_пересекаются(self) -> None:
        """Иначе категория одновременно считалась бы и объяснялась."""

        assert not set(RECORDABLE_CONTEXT.values()) & set(UNRECORDED_IMPACT)


@pytest.mark.anyio
async def test_сводка_не_показывает_нулей_по_неведущемуся(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """Экран больше не может МОЛЧА опустить категорию: причина приходит рядом."""

    headers = await make_auth_headers(RoleEnum.ADMIN)
    act = await _act(async_client, headers)
    detail = await async_client.get(f"{NPA}/{act['id']}", headers=headers)
    assert detail.status_code == 200, detail.text
    body = detail.json()

    # Счёт остаётся: связь может прийти импортом, и прятать существующую хуже,
    # чем показать ноль.
    for category in UNRECORDED_IMPACT:
        assert category in body["summary"]
    # Но рядом лежит причина, и её видно на экране.
    assert body["unrecorded"] == UNRECORDED_IMPACT


@pytest.mark.anyio
async def test_область_действия_записывается_и_считается(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory
) -> None:
    """То, ради чего срез: роль и площадка перестали быть вечным нулём."""

    headers = await make_auth_headers(RoleEnum.ADMIN)
    act = await _act(async_client, headers)
    document_id, site_id = await _seed(sessionmaker, data_factory)

    created = await async_client.post(
        f"{NPA}/{act['id']}/bindings",
        json={
            "entity_type": "document",
            "entity_id": document_id,
            "context": {"role_code": "worker", "site_id": site_id},
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    # Область действия возвращается СЛОВАМИ: код роли человек читать не должен.
    assert created.json()["context"]["role"] != "worker"
    assert created.json()["context"]["site"]

    detail = await async_client.get(f"{NPA}/{act['id']}", headers=headers)
    summary = detail.json()["summary"]
    assert summary["roles"] == 1, "роль не посчиталась — контекст снова не записан"
    assert summary["sites"] == 1


@pytest.mark.anyio
async def test_выдуманная_роль_отвергается(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory
) -> None:
    """Иначе «кого касается» снова стало бы свободной строкой."""

    headers = await make_auth_headers(RoleEnum.ADMIN)
    act = await _act(async_client, headers)
    document_id, _site_id = await _seed(sessionmaker, data_factory)
    response = await async_client.post(
        f"{NPA}/{act['id']}/bindings",
        json={
            "entity_type": "document",
            "entity_id": document_id,
            "context": {"role_code": "главный по тарелочкам"},
        },
        headers=headers,
    )
    assert response.status_code == 422, response.text


@pytest.mark.anyio
async def test_чужая_площадка_отвергается(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory
) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)
    act = await _act(async_client, headers)
    document_id, _site_id = await _seed(sessionmaker, data_factory)
    response = await async_client.post(
        f"{NPA}/{act['id']}/bindings",
        json={
            "entity_type": "document",
            "entity_id": document_id,
            "context": {"site_id": str(uuid4())},
        },
        headers=headers,
    )
    assert response.status_code == 404, response.text


@pytest.mark.anyio
async def test_лишний_ключ_области_отвергается(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory
) -> None:
    """Свободный словарь здесь уже был — именно из-за него сводка читала то,
    что никто не мог записать."""

    headers = await make_auth_headers(RoleEnum.ADMIN)
    act = await _act(async_client, headers)
    document_id, _site_id = await _seed(sessionmaker, data_factory)
    response = await async_client.post(
        f"{NPA}/{act['id']}/bindings",
        json={
            "entity_type": "document",
            "entity_id": document_id,
            "context": {"risk_id": "r-1"},
        },
        headers=headers,
    )
    assert response.status_code == 422, response.text


@pytest.mark.anyio
async def test_связь_без_области_остаётся_законной(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory
) -> None:
    """Пустая область — «касается всего акта», отдельное состояние, а не пробел."""

    headers = await make_auth_headers(RoleEnum.ADMIN)
    act = await _act(async_client, headers)
    document_id, _site_id = await _seed(sessionmaker, data_factory)
    response = await async_client.post(
        f"{NPA}/{act['id']}/bindings",
        json={"entity_type": "document", "entity_id": document_id},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    assert response.json()["context"] == {}
