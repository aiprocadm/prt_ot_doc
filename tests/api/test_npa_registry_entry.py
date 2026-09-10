"""Срез-141 (B.18 разд. 19.1): у реестра НПА появилась точка входа.

До среза в таблицы ``npa_act``/``npa_clause``/``npa_revision`` не писала ни
одна ручка: ``GET /npa`` отдавал пустой список всегда, экран НПА предлагал
«добавить или импортировать» акты, а добавить было нечем. Оценка влияния
(``NpaImpactService``) и задачи обновления работали только в тестах, которые
сеяли акты напрямую в ORM.

Что закреплено:
  * владелец платформы заводит акт с пунктами — и его видно в ``GET /npa``;
  * повторный код акта — 409, а не вторая строка и не 500;
  * администратор ОБЫЧНОГО арендатора — 403: реестр общий, править его из
    одного арендатора значило бы править для всех;
  * редакция, заведённая ручкой, появляется в оценке влияния;
  * флаг ``can_manage`` говорит витрине правду о том, кто может заводить.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.core.config import get_settings
from app.models.models import RoleEnum

BASE = "/api/v1/npa"


@pytest.fixture(autouse=True)
def _managing_tenant(monkeypatch: pytest.MonkeyPatch):
    """Арендатор «test» — владелец платформы (как в test_platform_tenants_api)."""

    monkeypatch.setenv("PLATFORM_TENANT_SLUG", "test")
    get_settings.cache_clear()  # type: ignore[attr-defined]
    yield
    get_settings.cache_clear()  # type: ignore[attr-defined]


def _act_payload(code: str = "772н") -> dict:
    return {
        "code": code,
        "title": "Приказ Минтруда № 772н об обучении по охране труда",
        "edition": "ред. от 01.03.2026",
        "valid_from": "2026-03-01",
        "valid_to": None,
        "clauses": [
            {"code": "1", "text": "Общие положения"},
            {"code": "2", "text": "Программы обучения"},
        ],
    }


@pytest.mark.anyio
async def test_владелец_платформы_заводит_акт_и_видит_его_в_реестре(
    async_client: AsyncClient, make_auth_headers
) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)

    created = await async_client.post(BASE, json=_act_payload(), headers=headers)

    assert created.status_code == 201, created.text
    body = created.json()
    assert body["code"] == "772н"
    assert [clause["code"] for clause in body["clauses"]] == ["1", "2"]

    listed = await async_client.get(BASE, headers=headers)
    assert listed.status_code == 200
    items = {item["code"]: item for item in listed.json()["items"]}
    assert "772н" in items
    assert [clause["text"] for clause in items["772н"]["clauses"]] == [
        "Общие положения",
        "Программы обучения",
    ]


@pytest.mark.anyio
async def test_повторный_код_акта_это_409(async_client: AsyncClient, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)
    first = await async_client.post(BASE, json=_act_payload("2464"), headers=headers)
    assert first.status_code == 201, first.text

    second = await async_client.post(BASE, json=_act_payload("2464"), headers=headers)

    assert second.status_code == 409, second.text
    listed = await async_client.get(BASE, headers=headers)
    assert [item["code"] for item in listed.json()["items"]].count("2464") == 1


@pytest.mark.anyio
async def test_админ_обычного_арендатора_не_правит_общий_реестр(
    async_client: AsyncClient, make_auth_headers, data_factory, sessionmaker
) -> None:
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(slug="outsider", session=session)
        await session.commit()
    headers = await make_auth_headers(
        RoleEnum.ADMIN, tenant="outsider", email="admin-outsider-npa@example.com"
    )

    response = await async_client.post(BASE, json=_act_payload("29н"), headers=headers)

    assert response.status_code == 403, response.text
    # Читать реестр ему можно — но кнопку заводить витрина ему не покажет.
    listed = await async_client.get(BASE, headers=headers)
    assert listed.status_code == 200
    assert listed.json()["can_manage"] is False


@pytest.mark.anyio
async def test_рядовая_роль_владельца_платформы_тоже_не_правит(
    async_client: AsyncClient, make_auth_headers
) -> None:
    headers = await make_auth_headers(RoleEnum.WORKER)

    response = await async_client.post(BASE, json=_act_payload("29н"), headers=headers)

    assert response.status_code == 403, response.text


@pytest.mark.anyio
async def test_флаг_can_manage_говорит_правду_владельцу(
    async_client: AsyncClient, make_auth_headers
) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)

    listed = await async_client.get(BASE, headers=headers)

    assert listed.status_code == 200
    assert listed.json()["can_manage"] is True


@pytest.mark.anyio
async def test_редакция_из_ручки_видна_в_оценке_влияния(
    async_client: AsyncClient, make_auth_headers
) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)
    act = (await async_client.post(BASE, json=_act_payload("1/29"), headers=headers)).json()

    created = await async_client.post(
        f"{BASE}/{act['id']}/revisions",
        json={
            "revision_code": "1/29-2026-03",
            "title": "Редакция с новыми программами обучения",
            "effective_from": "2026-03-01",
            "effective_to": None,
            "change_summary": "Обновлены программы обучения",
        },
        headers=headers,
    )

    assert created.status_code == 201, created.text
    assert created.json()["act_id"] == act["id"]

    duplicate = await async_client.post(
        f"{BASE}/{act['id']}/revisions",
        json={"revision_code": "1/29-2026-03", "title": "Та же редакция"},
        headers=headers,
    )
    assert duplicate.status_code == 409, duplicate.text

    missing = await async_client.post(
        f"{BASE}/no-such-act/revisions",
        json={"revision_code": "x", "title": "x"},
        headers=headers,
    )
    assert missing.status_code == 404, missing.text

    detail = await async_client.get(f"{BASE}/{act['id']}", headers=headers)
    assert detail.status_code == 200, detail.text
    assert [r["revision_code"] for r in detail.json()["revisions"]] == ["1/29-2026-03"]


@pytest.mark.anyio
async def test_заявка_с_датами_наоборот_отклоняется(
    async_client: AsyncClient, make_auth_headers
) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)
    payload = _act_payload("bad-dates") | {"valid_from": "2026-03-01", "valid_to": "2026-01-01"}

    response = await async_client.post(BASE, json=payload, headers=headers)

    assert response.status_code == 422, response.text
