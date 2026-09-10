"""Срез-142 (B.18 разд. 19.3): связи акта с документами арендатора заводятся ручкой.

До среза в ``npabinding`` не писал никто, а внешний ключ ``npa_id`` смотрел в
арендаторскую таблицу ``npa`` (пустую всегда), тогда как оценка влияния
сравнивала его с ``npa_act.id``. Мина не стреляла только потому, что связей не
было. Теперь ``npa_id`` ведёт в общий реестр, связь заводится
``POST /npa/{act_id}/bindings``, снимается ``DELETE``, а оценка влияния и карта
зависимостей документа считают по ней.

Что закреплено:
  * привязка документа — 201, и оценка влияния видит её с именем документа;
  * повтор той же связи — 409, а не вторая строка;
  * чужой/несуществующий документ и несуществующий акт — 404;
  * рядовая роль — 403 (тот же круг, что у задач по оценке влияния);
  * связь видна в карте зависимостей документа с кодом и названием акта;
  * задачи обновления создаются по связям, а не по пустоте;
  * отвязка — 204, и оценка влияния снова пуста; версия шаблона и пакет —
    те же правила.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.core.config import get_settings
from app.models.models import RoleEnum
from app.models.packages import DocumentPack
from app.models.templates import TemplateVersion

BASE = "/api/v1/npa"


@pytest.fixture(autouse=True)
def _managing_tenant(monkeypatch: pytest.MonkeyPatch):
    """Акты заводит владелец платформы — арендатор «test» (как в срезе-141)."""

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


async def _seed_document(sessionmaker, data_factory) -> dict[str, str]:
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
        return {
            "document_id": document.id,
            "template_id": template.id,
            "template_name": template.name,
            "company_name": company.name,
        }


@pytest.mark.anyio
async def test_привязка_документа_видна_в_оценке_влияния_и_карте_зависимостей(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory
) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)
    act = await _create_act(async_client, headers)
    seeded = await _seed_document(sessionmaker, data_factory)

    before = await async_client.get(f"{BASE}/{act['id']}", headers=headers)
    assert before.json()["summary"]["documents"] == 0
    assert before.json()["binding_items"] == []

    created = await async_client.post(
        f"{BASE}/{act['id']}/bindings",
        json={"entity_type": "document", "entity_id": seeded["document_id"], "ref": "п. 4"},
        headers=headers,
    )

    assert created.status_code == 201, created.text
    body = created.json()
    assert body["entity_type"] == "document"
    assert body["entity_id"] == seeded["document_id"]
    assert body["ref"] == "п. 4"
    assert body["title"] == f"{seeded['template_name']} · {seeded['company_name']}"

    detail = await async_client.get(f"{BASE}/{act['id']}", headers=headers)
    assert detail.status_code == 200, detail.text
    payload = detail.json()
    assert payload["summary"]["documents"] == 1
    assert payload["bindings"]["documents"] == [seeded["document_id"]]
    assert [item["title"] for item in payload["binding_items"]] == [body["title"]]
    assert payload["binding_items"][0]["id"] == body["id"]
    assert payload["tasks_to_create"] == [
        {
            "code": "npa-update-documents",
            "title": "Актуализировать зависимости НПА: documents",
            "count": 1,
        }
    ]

    dependency_map = await async_client.get(
        f"/api/v1/documents/{seeded['document_id']}/dependency-map", headers=headers
    )
    assert dependency_map.status_code == 200, dependency_map.text
    npa_bindings = dependency_map.json()["npa_bindings"]
    assert [(b["npa_code"], b["npa_title"], b["ref"]) for b in npa_bindings] == [
        (act["code"], act["title"], "п. 4")
    ]


@pytest.mark.anyio
async def test_задачи_обновления_считаются_по_связям(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory
) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)
    act = await _create_act(async_client, headers)

    empty = await async_client.post(f"{BASE}/{act['id']}/impact/tasks", headers=headers)
    assert empty.status_code == 200, empty.text
    assert empty.json()["created"] == 0

    seeded = await _seed_document(sessionmaker, data_factory)
    bound = await async_client.post(
        f"{BASE}/{act['id']}/bindings",
        json={"entity_type": "document", "entity_id": seeded["document_id"]},
        headers=headers,
    )
    assert bound.status_code == 201, bound.text

    created = await async_client.post(f"{BASE}/{act['id']}/impact/tasks", headers=headers)
    assert created.status_code == 200, created.text
    assert created.json()["created"] == 1
    assert created.json()["items"][0]["title"] == "Актуализировать зависимости НПА: documents"


@pytest.mark.anyio
async def test_повтор_связи_это_409_а_чужое_и_несуществующее_404(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory
) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)
    act = await _create_act(async_client, headers)
    seeded = await _seed_document(sessionmaker, data_factory)
    body = {"entity_type": "document", "entity_id": seeded["document_id"]}

    first = await async_client.post(f"{BASE}/{act['id']}/bindings", json=body, headers=headers)
    assert first.status_code == 201, first.text
    second = await async_client.post(f"{BASE}/{act['id']}/bindings", json=body, headers=headers)
    assert second.status_code == 409, second.text
    detail = await async_client.get(f"{BASE}/{act['id']}", headers=headers)
    assert detail.json()["summary"]["documents"] == 1

    ghost = await async_client.post(
        f"{BASE}/{act['id']}/bindings",
        json={"entity_type": "document", "entity_id": str(uuid4())},
        headers=headers,
    )
    assert ghost.status_code == 404, ghost.text

    # Документ другого арендатора — для этого арендатора его нет.
    async with sessionmaker() as session:
        outsider = await data_factory.ensure_tenant(slug="outsider-npa", session=session)
        foreign, _ = await data_factory.create_document(tenant=outsider, session=session)
        await session.commit()
    stranger = await async_client.post(
        f"{BASE}/{act['id']}/bindings",
        json={"entity_type": "document", "entity_id": foreign.id},
        headers=headers,
    )
    assert stranger.status_code == 404, stranger.text

    no_act = await async_client.post(f"{BASE}/no-such-act/bindings", json=body, headers=headers)
    assert no_act.status_code == 404, no_act.text


@pytest.mark.anyio
async def test_рядовая_роль_не_заводит_связи(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory
) -> None:
    admin = await make_auth_headers(RoleEnum.ADMIN)
    act = await _create_act(async_client, admin)
    seeded = await _seed_document(sessionmaker, data_factory)
    worker = await make_auth_headers(RoleEnum.WORKER)

    response = await async_client.post(
        f"{BASE}/{act['id']}/bindings",
        json={"entity_type": "document", "entity_id": seeded["document_id"]},
        headers=worker,
    )

    assert response.status_code == 403, response.text


@pytest.mark.anyio
async def test_отвязка_убирает_связь_из_оценки_влияния(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory
) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)
    act = await _create_act(async_client, headers)
    seeded = await _seed_document(sessionmaker, data_factory)
    created = await async_client.post(
        f"{BASE}/{act['id']}/bindings",
        json={"entity_type": "document", "entity_id": seeded["document_id"]},
        headers=headers,
    )
    binding_id = created.json()["id"]

    deleted = await async_client.delete(
        f"{BASE}/{act['id']}/bindings/{binding_id}", headers=headers
    )

    assert deleted.status_code == 204, deleted.text
    detail = await async_client.get(f"{BASE}/{act['id']}", headers=headers)
    assert detail.json()["summary"]["documents"] == 0
    assert detail.json()["binding_items"] == []
    again = await async_client.delete(f"{BASE}/{act['id']}/bindings/{binding_id}", headers=headers)
    assert again.status_code == 404, again.text


@pytest.mark.anyio
async def test_версия_шаблона_и_пакет_привязываются_с_именами(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory
) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)
    act = await _create_act(async_client, headers)
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        template = await data_factory.create_template(
            tenant=tenant, name=f"Программа {uuid4().hex[:4]}", session=session
        )
        version = TemplateVersion(
            tenant_id=tenant.id,
            template_id=template.id,
            version=3,
            checksum=b"v3",
            sha256="v3",
            payload_key="templates/v3.docx",
        )
        pack = DocumentPack(
            tenant_id=tenant.id, code=f"pack-{uuid4().hex[:6]}", name="Пакет для стройки"
        )
        session.add_all([version, pack])
        await session.commit()
        version_id, pack_id, template_name = version.id, pack.id, template.name

    bound_version = await async_client.post(
        f"{BASE}/{act['id']}/bindings",
        json={"entity_type": "template_version", "entity_id": version_id},
        headers=headers,
    )
    assert bound_version.status_code == 201, bound_version.text
    assert bound_version.json()["title"] == f"{template_name} v3"

    bound_pack = await async_client.post(
        f"{BASE}/{act['id']}/bindings",
        json={"entity_type": "pack", "entity_id": pack_id},
        headers=headers,
    )
    assert bound_pack.status_code == 201, bound_pack.text
    assert bound_pack.json()["title"] == "Пакет для стройки"

    detail = await async_client.get(f"{BASE}/{act['id']}", headers=headers)
    payload = detail.json()
    assert payload["summary"]["templates"] == 1
    assert payload["summary"]["packages"] == 1
    assert {item["entity_type"] for item in payload["binding_items"]} == {
        "template_version",
        "pack",
    }
    assert {t["code"] for t in payload["tasks_to_create"]} == {
        "npa-update-templates",
        "npa-update-packages",
    }
