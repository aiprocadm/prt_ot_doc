"""Собственные акты арендатора: B.18 разд. 19.1 (срез-201).

ЧТО БЫЛО. Реестр НПА знал только федеральные акты, которые заводит владелец
платформы. Свой приказ по организации («О назначении ответственного за
электрохозяйство») записать было НЕЧЕМ: у таблицы ``npa_act`` не было хозяина,
код акта был уникален на всю платформу, а единственная ручка заведения
пускала только владельца платформы.

Это не мелкая недоделка. Вся обвязка вокруг акта уже была построена —
редакции, пункты, связи с документами, требования реестра, оценка влияния,
задачи актуализации, — и целиком не работала для той половины нормативки,
которую организация пишет себе сама.

ЧТО ЗАКРЕПЛЕНО ЗДЕСЬ.

1. Арендатор заводит собственный акт и видит его; владелец платформы — нет.
   Локальный приказ — нормативка арендатора, а не платформы.
2. ДВА арендатора заводят «Приказ №1» ОДНОВРЕМЕННО. Это главный тест среза:
   пока код был уникален глобально, приказ доставался первому, кто успел, а
   второму отвечали 409 про акт, которого он даже не видит.
3. Чужой локальный акт не достаётся ни по прямой ссылке, ни связью, ни
   требованием, ни поиском — то есть ни в одном из мест, которые до среза
   спрашивали таблицу напрямую.
4. Общий реестр по-прежнему закрыт: обычный арендатор не может дописать в
   него федеральный акт, и повторный код там по-прежнему 409.

ЗАПУСК: ``PYTHONPATH=backend pytest tests/api/test_npa_tenant_acts.py -v``.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings
from app.models.models import RoleEnum
from app.models.npa import NpaAct

NPA = "/api/v1/npa"
REQUIREMENTS = "/api/v1/compliance/requirements"


@pytest.fixture(autouse=True)
def _managing_tenant(monkeypatch: pytest.MonkeyPatch):
    """Арендатор «test» — владелец платформы, как в соседних тестах реестра."""

    monkeypatch.setenv("PLATFORM_TENANT_SLUG", "test")
    get_settings.cache_clear()  # type: ignore[attr-defined]
    yield
    get_settings.cache_clear()  # type: ignore[attr-defined]


def _own_act(code: str, title: str = "Приказ по организации") -> dict:
    return {
        "scope": "own",
        "code": code,
        "title": title,
        "edition": "ред. 2026",
        "valid_from": "2026-01-01",
        "clauses": [{"code": "1", "text": "Назначить ответственного"}],
    }


async def _tenant_headers(make_auth_headers, data_factory, sessionmaker, slug: str) -> dict:
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(slug=slug, session=session)
        await session.commit()
    return await make_auth_headers(
        RoleEnum.ADMIN, tenant=slug, email=f"admin-{slug}-npa201@example.com"
    )


@pytest.mark.anyio
async def test_арендатор_заводит_свой_приказ_и_видит_его(
    async_client: AsyncClient, make_auth_headers, data_factory, sessionmaker
) -> None:
    headers = await _tenant_headers(make_auth_headers, data_factory, sessionmaker, "acme201")

    created = await async_client.post(NPA, json=_own_act("ПР-1"), headers=headers)

    assert created.status_code == 201, created.text
    body = created.json()
    # Ящик приходит и кодом, и словами: витрина не должна знать, что "own" —
    # это «акт организации».
    assert body["scope"] == "own"
    assert body["scope_title"] == "Акт организации"

    listed = await async_client.get(NPA, headers=headers)
    mine = {item["code"]: item for item in listed.json()["items"]}
    assert "ПР-1" in mine
    assert mine["ПР-1"]["scope"] == "own"
    # Право «завести свой акт» — отдельное от права «править общий реестр».
    assert listed.json()["can_create_own"] is True
    assert listed.json()["can_manage"] is False


@pytest.mark.anyio
async def test_один_код_приказа_у_двух_арендаторов(
    async_client: AsyncClient, make_auth_headers, data_factory, sessionmaker
) -> None:
    """ГЛАВНЫЙ ТЕСТ СРЕЗА.

    «Приказ №1» есть у КАЖДОЙ организации. Пока код акта был уникален на всю
    платформу, он доставался первому, кто успел, а остальным система отвечала
    «такой акт уже есть» — про акт, которого они даже не видят.
    """

    first = await _tenant_headers(make_auth_headers, data_factory, sessionmaker, "alpha201")
    second = await _tenant_headers(make_auth_headers, data_factory, sessionmaker, "beta201")

    a = await async_client.post(NPA, json=_own_act("ПРИКАЗ-1", "Приказ Альфы"), headers=first)
    b = await async_client.post(NPA, json=_own_act("ПРИКАЗ-1", "Приказ Беты"), headers=second)

    assert a.status_code == 201, a.text
    assert b.status_code == 201, b.text
    assert a.json()["id"] != b.json()["id"]

    # И каждый видит ТОЛЬКО свой.
    a_codes = {
        item["id"]: item["title"]
        for item in (await async_client.get(NPA, headers=first)).json()["items"]
    }
    assert a_codes.get(a.json()["id"]) == "Приказ Альфы"
    assert b.json()["id"] not in a_codes


@pytest.mark.anyio
async def test_свой_код_дважды_это_409(
    async_client: AsyncClient, make_auth_headers, data_factory, sessionmaker
) -> None:
    """Внутри одной организации код по-прежнему занят один раз: иначе «Приказ
    №1» стал бы неоднозначным уже у самого арендатора."""

    headers = await _tenant_headers(make_auth_headers, data_factory, sessionmaker, "gamma201")
    first = await async_client.post(NPA, json=_own_act("ПР-7"), headers=headers)
    assert first.status_code == 201, first.text

    second = await async_client.post(NPA, json=_own_act("ПР-7"), headers=headers)

    assert second.status_code == 409, second.text


@pytest.mark.anyio
async def test_чужой_приказ_не_виден_никак(
    async_client: AsyncClient, make_auth_headers, data_factory, sessionmaker
) -> None:
    """Вторая половина среза: спрашивать акты можно девятью способами, и все
    девять должны отвечать одинаково — «нет такого»."""

    owner = await _tenant_headers(make_auth_headers, data_factory, sessionmaker, "delta201")
    stranger = await _tenant_headers(make_auth_headers, data_factory, sessionmaker, "epsilon201")
    created = await async_client.post(
        NPA, json=_own_act(f"СЕКРЕТ-{uuid4().hex[:4]}"), headers=owner
    )
    assert created.status_code == 201, created.text
    act_id = created.json()["id"]

    # 1. Списком не приходит.
    listed = await async_client.get(NPA, headers=stranger)
    assert act_id not in {item["id"] for item in listed.json()["items"]}

    # 2. По прямой ссылке — 404, а не текст чужого приказа. Именно здесь до
    #    среза стоял `session.get(NpaAct, act_id)`: он берёт строку по ключу и
    #    условий не принимает ВООБЩЕ.
    detail = await async_client.get(f"{NPA}/{act_id}", headers=stranger)
    assert detail.status_code == 404, detail.text

    # 3. Связь на чужой акт не заводится.
    binding = await async_client.post(
        f"{NPA}/{act_id}/bindings",
        json={"entity_type": "document", "entity_id": str(uuid4())},
        headers=stranger,
    )
    assert binding.status_code == 404, binding.text

    # 4. Требование по чужому акту не заводится — иначе его код и название
    #    вычитались бы прямо из карточки требования.
    requirement = await async_client.post(
        REQUIREMENTS,
        json={"code": f"ОТ-{uuid4().hex[:6]}", "title": "Проверить", "npa_id": act_id},
        headers=stranger,
    )
    assert requirement.status_code == 404, requirement.text


@pytest.mark.anyio
async def test_владельцу_платформы_чужой_локальный_акт_тоже_не_виден(
    async_client: AsyncClient, make_auth_headers, data_factory, sessionmaker
) -> None:
    """Локальный приказ — нормативка арендатора, а не платформы.

    Соблазн «владелец платформы видит всё» здесь неверен: в приказе по
    организации есть фамилии и структура подразделений, и заводился он не для
    платформы.
    """

    owner = await _tenant_headers(make_auth_headers, data_factory, sessionmaker, "zeta201")
    created = await async_client.post(NPA, json=_own_act("ПР-ЗЕТА"), headers=owner)
    assert created.status_code == 201, created.text

    platform = await make_auth_headers(RoleEnum.ADMIN)
    listed = await async_client.get(NPA, headers=platform)
    assert created.json()["id"] not in {item["id"] for item in listed.json()["items"]}
    detail = await async_client.get(f"{NPA}/{created.json()['id']}", headers=platform)
    assert detail.status_code == 404, detail.text


@pytest.mark.anyio
async def test_общий_реестр_по_прежнему_закрыт(
    async_client: AsyncClient, make_auth_headers, data_factory, sessionmaker
) -> None:
    """Срез добавил ВТОРОЙ ящик, а не открыл первый.

    Дописать в общий реестр из одного арендатора значило бы дописать его всем —
    ровно то, что запрещал срез-141, и запрет не ослаблен.
    """

    headers = await _tenant_headers(make_auth_headers, data_factory, sessionmaker, "eta201")
    payload = _own_act("ФЕД-1")
    payload["scope"] = "registry"

    response = await async_client.post(NPA, json=payload, headers=headers)

    assert response.status_code == 403, response.text


@pytest.mark.anyio
async def test_рядовая_роль_не_заводит_даже_свой_акт(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """Свой приказ — тоже нормативка: её ведёт тот, кто отвечает за охрану
    труда, а не любой работник."""

    headers = await make_auth_headers(RoleEnum.WORKER)

    response = await async_client.post(NPA, json=_own_act("ПР-9"), headers=headers)

    assert response.status_code == 403, response.text


@pytest.mark.anyio
async def test_арендатор_ведёт_редакции_своего_акта(
    async_client: AsyncClient, make_auth_headers, data_factory, sessionmaker
) -> None:
    """Редакция своего приказа — это «мы его переиздали». Без неё собственный
    акт остался бы мёртвой карточкой: именно редакции помечают связи
    непересмотренными и поднимают задачи актуализации."""

    headers = await _tenant_headers(make_auth_headers, data_factory, sessionmaker, "theta201")
    act = await async_client.post(NPA, json=_own_act("ПР-ТЕТА"), headers=headers)
    assert act.status_code == 201, act.text

    revision = await async_client.post(
        f"{NPA}/{act.json()['id']}/revisions",
        json={
            "revision_code": "ред-2",
            "title": "Переиздан",
            "effective_from": "2026-02-01",
        },
        headers=headers,
    )

    assert revision.status_code == 201, revision.text


@pytest.mark.anyio
async def test_чужую_редакцию_не_завести(
    async_client: AsyncClient, make_auth_headers, data_factory, sessionmaker
) -> None:
    owner = await _tenant_headers(make_auth_headers, data_factory, sessionmaker, "iota201")
    stranger = await _tenant_headers(make_auth_headers, data_factory, sessionmaker, "kappa201")
    act = await async_client.post(NPA, json=_own_act("ПР-ЙОТА"), headers=owner)

    response = await async_client.post(
        f"{NPA}/{act.json()['id']}/revisions",
        json={"revision_code": "ред-2", "title": "Чужая", "effective_from": "2026-02-01"},
        headers=stranger,
    )

    assert response.status_code == 404, response.text


@pytest.mark.anyio
async def test_редакцию_федерального_акта_арендатор_не_заводит(
    async_client: AsyncClient, make_auth_headers, data_factory, sessionmaker
) -> None:
    """Видеть общий акт можно всем, а переиздавать его — только владельцу
    платформы: иначе один арендатор менял бы правила остальным."""

    platform = await make_auth_headers(RoleEnum.ADMIN)
    federal = await async_client.post(
        NPA,
        json={
            "code": f"ФЕД-{uuid4().hex[:5]}",
            "title": "Приказ Минтруда",
            "edition": "ред. 2026",
            "valid_from": "2026-01-01",
            "clauses": [{"code": "1", "text": "Общие положения"}],
        },
        headers=platform,
    )
    assert federal.status_code == 201, federal.text

    tenant = await _tenant_headers(make_auth_headers, data_factory, sessionmaker, "lambda201")
    # Видеть — да.
    detail = await async_client.get(f"{NPA}/{federal.json()['id']}", headers=tenant)
    assert detail.status_code == 200, detail.text
    assert detail.json()["act"]["scope"] == "registry"
    assert detail.json()["act"]["scope_title"] == "Общий реестр"

    # Переиздавать — нет.
    response = await async_client.post(
        f"{NPA}/{federal.json()['id']}/revisions",
        json={"revision_code": "ред-2", "title": "Своя правка", "effective_from": "2026-02-01"},
        headers=tenant,
    )
    assert response.status_code == 403, response.text


@pytest.mark.anyio
async def test_уникальность_держит_база_а_не_только_проверка_в_коде(sessionmaker) -> None:
    """Проверка кода в ручке — не замена индексу.

    Две одинаковые заявки, пришедшие одновременно, проходят проверку «такого
    кода нет» ОБЕ: между чтением и записью проходит время. От второй строки
    спасает только база. Здесь запись идёт мимо ручки — именно чтобы увидеть
    базу, а не проверку перед ней.
    """

    code = f"ДУБЛЬ-{uuid4().hex[:6]}"
    async with sessionmaker() as session:
        session.add(NpaAct(code=code, title="Первый", edition="ред. 1"))
        await session.commit()

    async with sessionmaker() as session:
        session.add(NpaAct(code=code, title="Второй", edition="ред. 1"))
        with pytest.raises(IntegrityError):
            await session.commit()


@pytest.mark.anyio
async def test_один_код_у_разных_владельцев_база_пропускает(sessionmaker) -> None:
    """Обратная сторона: индексы не должны запретить лишнего.

    Если частичные условия перепутать, «Приказ №1» снова достанется одному
    арендатору — и поймать это можно только проверкой С ДРУГОЙ СТОРОНЫ.
    """

    code = f"ОБЩИЙ-{uuid4().hex[:6]}"
    async with sessionmaker() as session:
        session.add(NpaAct(code=code, title="Федеральный", edition="ред. 1"))
        session.add(NpaAct(code=code, title="Альфы", edition="ред. 1", owner_tenant_id="t-alpha"))
        session.add(NpaAct(code=code, title="Беты", edition="ред. 1", owner_tenant_id="t-beta"))
        await session.commit()

    async with sessionmaker() as session:
        session.add(
            NpaAct(code=code, title="Альфы ещё раз", edition="ред. 1", owner_tenant_id="t-alpha")
        )
        with pytest.raises(IntegrityError):
            await session.commit()
