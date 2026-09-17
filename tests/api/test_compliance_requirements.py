"""Срез-145 (B.18 разд. 19.2): реестр требований — обязательное ядро арендатора.

До среза платформа знала, какие ДОКУМЕНТЫ зависят от акта (связи НПА), но не
знала, какие ОБЯЗАННОСТИ из него следуют. Реестр требований — эти
обязанности как строки: откуда (акт/пункт), к кому (роль/площадка/процесс),
кто отвечает, как часто, до какой даты, чем доказано, насколько серьёзно
неисполнение.

Что закреплено:
  * требование заводится с привязкой к акту и пункту, код уникален (409);
  * список считает «просрочено» и «дней осталось» по UTC-«сегодня»;
  * доказательство исполнения сдвигает контрольную дату на период от дня
    подтверждения; разовое требование — закрывается (``fulfilled``);
  * «снять с контроля» — ``retired``, из просрочки уходит, удаления нет;
  * оценка влияния акта показывает число активных требований из него;
  * Центр внимания: просроченное — ``critical``/``high`` и совет; ответственный
    без обзора видит своё, другой работник — нет;
  * рядовая роль — 403 на запись, чужой арендатор — 404, работник видит
    в списке только своё.

Даты — в далёком прошлом/будущем нарочно: «сегодня» у продукта по UTC, у
процесса тестов — по Москве, вечером это разные дни (срез-140).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.config import get_settings
from app.models.identity import User
from app.models.master_data import Site
from app.models.models import RoleEnum

BASE = "/api/v1/compliance/requirements"
NPA = "/api/v1/npa"
ATTENTION = "/api/v1/workspace/attention"

#: Заведомо в прошлом и заведомо в будущем — вне любого полуночного окна.
PAST = date(2020, 1, 15)
FAR_FUTURE = date(2999, 1, 1)


@pytest.fixture(autouse=True)
def _managing_tenant(monkeypatch: pytest.MonkeyPatch):
    """Акты общего реестра заводит владелец платформы — арендатор «test»."""

    monkeypatch.setenv("PLATFORM_TENANT_SLUG", "test")
    get_settings.cache_clear()  # type: ignore[attr-defined]
    yield
    get_settings.cache_clear()  # type: ignore[attr-defined]


async def _create_act(client: AsyncClient, headers: dict[str, str]) -> dict:
    response = await client.post(
        NPA,
        json={
            "code": f"{uuid4().hex[:6]}н",
            "title": "Приказ об обучении по охране труда",
            "edition": "ред. 2026",
            "valid_from": "2026-01-01",
            "clauses": [{"code": "п. 4", "text": "Обучение проводится не реже раза в год"}],
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _create(client: AsyncClient, headers: dict[str, str], **fields) -> dict:
    payload = {
        "code": f"ОТ-{uuid4().hex[:6]}",
        "title": "Проводить обучение по охране труда",
        "severity": "high",
        **fields,
    }
    response = await client.post(BASE, json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


async def _user_id(sessionmaker, email: str) -> str:
    async with sessionmaker() as session:
        user = await session.scalar(select(User).where(User.email == email))
        assert user is not None
        return user.id


def _requirement_items(attention: dict, requirement_id: str) -> list[dict]:
    return [
        item
        for item in attention["items"]
        if item["item_type"] == "compliance_requirement" and item["entity_id"] == requirement_id
    ]


@pytest.mark.anyio
async def test_требование_заводится_с_актом_и_пунктом_и_видно_в_оценке_влияния(
    async_client: AsyncClient, make_auth_headers
) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)
    act = await _create_act(async_client, headers)
    clause = act["clauses"][0]

    created = await _create(
        async_client,
        headers,
        npa_id=act["id"],
        clause_id=clause["id"],
        role_code="ot_specialist",
        process_code="training",
        periodicity_days=365,
        next_due_at=FAR_FUTURE.isoformat(),
        description="Обучение работников рабочих профессий",
    )
    assert created["status"] == "active"
    assert created["npa_code"] == act["code"]
    assert created["npa_title"] == act["title"]
    assert created["clause_code"] == "п. 4"
    assert created["overdue"] is False
    assert created["days_left"] > 0
    assert created["evidence"] == []
    assert created["evidence_count"] == 0

    # Дубликат кода — 409, а не 500.
    duplicate = await async_client.post(
        BASE, json={"code": created["code"], "title": "Ещё раз"}, headers=headers
    )
    assert duplicate.status_code == 409, duplicate.text

    # Ссылка на несуществующий акт — 404 с понятным словом.
    missing = await async_client.post(
        BASE,
        json={"code": f"X-{uuid4().hex[:4]}", "title": "Без акта", "npa_id": str(uuid4())},
        headers=headers,
    )
    assert missing.status_code == 404, missing.text

    detail = (await async_client.get(f"{NPA}/{act['id']}", headers=headers)).json()
    assert detail["summary"]["requirements"] == 1
    assert detail["bindings"]["requirements"] == [created["id"]]
    # Требование — не связь: задач актуализации по нему не заводится.
    assert detail["tasks_to_create"] == []

    listing = (await async_client.get(BASE, params={"npa_id": act["id"]}, headers=headers)).json()
    assert [item["id"] for item in listing["items"]] == [created["id"]]
    assert listing["can_manage"] is True
    assert listing["active"] == 1
    assert listing["overdue"] == 0


@pytest.mark.anyio
async def test_доказательство_сдвигает_срок_а_разовое_закрывается(
    async_client: AsyncClient, make_auth_headers, sessionmaker
) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)
    admin_id = await _user_id(sessionmaker, "admin-api@example.com")

    periodic = await _create(
        async_client, headers, periodicity_days=365, next_due_at=PAST.isoformat()
    )
    assert periodic["overdue"] is True
    assert periodic["days_left"] < 0
    one_off = await _create(async_client, headers, next_due_at=PAST.isoformat())

    listing = (await async_client.get(BASE, params={"overdue": "true"}, headers=headers)).json()
    assert {item["id"] for item in listing["items"]} == {periodic["id"], one_off["id"]}
    assert listing["overdue"] == 2

    # Ни документа, ни заметки — нечем доказать.
    empty = await async_client.post(f"{BASE}/{periodic['id']}/evidence", json={}, headers=headers)
    assert empty.status_code == 422, empty.text

    confirmed_on = date(2020, 3, 1)
    confirmed = await async_client.post(
        f"{BASE}/{periodic['id']}/evidence",
        json={"note": "Протокол обучения № 7", "confirmed_at": confirmed_on.isoformat()},
        headers=headers,
    )
    assert confirmed.status_code == 201, confirmed.text
    body = confirmed.json()
    # Срок считается от дня подтверждения, а не от старой контрольной даты.
    assert body["next_due_at"] == (confirmed_on + timedelta(days=365)).isoformat()
    assert body["last_confirmed_at"] == confirmed_on.isoformat()
    assert body["status"] == "active"
    assert body["evidence_count"] == 1
    assert body["evidence"][0]["note"] == "Протокол обучения № 7"
    assert body["evidence"][0]["confirmed_by"] == admin_id

    closed = await async_client.post(
        f"{BASE}/{one_off['id']}/evidence",
        json={"note": "Инструкция утверждена"},
        headers=headers,
    )
    assert closed.status_code == 201, closed.text
    assert closed.json()["status"] == "fulfilled"
    assert closed.json()["overdue"] is False

    listing = (await async_client.get(BASE, params={"overdue": "true"}, headers=headers)).json()
    # Периодическое всё ещё просрочено (2021 год давно прошёл), разовое ушло.
    assert {item["id"] for item in listing["items"]} == {periodic["id"]}

    retired = await async_client.post(f"{BASE}/{periodic['id']}/retire", headers=headers)
    assert retired.status_code == 200, retired.text
    assert retired.json()["status"] == "retired"
    assert retired.json()["retired_at"] is not None
    assert retired.json()["overdue"] is False
    listing = (await async_client.get(BASE, params={"overdue": "true"}, headers=headers)).json()
    assert listing["items"] == []
    # Снятое с контроля остаётся в реестре — с доказательствами.
    detail = (await async_client.get(f"{BASE}/{periodic['id']}", headers=headers)).json()
    assert detail["status"] == "retired"
    assert detail["evidence_count"] == 1


@pytest.mark.anyio
async def test_правка_и_снятие_с_контроля_только_ролям_записи(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory
) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)
    created = await _create(async_client, headers, next_due_at=FAR_FUTURE.isoformat())

    patched = await async_client.patch(
        f"{BASE}/{created['id']}",
        json={"severity": "critical", "periodicity_days": 30},
        headers=headers,
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["severity"] == "critical"
    assert patched.json()["periodicity_days"] == 30
    assert patched.json()["code"] == created["code"]

    worker = await make_auth_headers(RoleEnum.WORKER)
    for method, path, body in (
        ("post", BASE, {"code": "W-1", "title": "Нельзя"}),
        ("patch", f"{BASE}/{created['id']}", {"title": "Нельзя"}),
        ("post", f"{BASE}/{created['id']}/evidence", {"note": "Нельзя"}),
        ("post", f"{BASE}/{created['id']}/retire", None),
    ):
        response = await async_client.request(method.upper(), path, json=body, headers=worker)
        assert response.status_code == 403, (method, path, response.text)

    # Работник без ответственности реестр не видит — ни списком, ни по id.
    listing = (await async_client.get(BASE, headers=worker)).json()
    assert listing["items"] == []
    assert listing["can_manage"] is False
    hidden = await async_client.get(f"{BASE}/{created['id']}", headers=worker)
    assert hidden.status_code == 404, hidden.text

    async with sessionmaker() as session:
        await data_factory.ensure_tenant(slug="outsider", session=session)
        await session.commit()
    outsider = await make_auth_headers(
        RoleEnum.ADMIN, tenant="outsider", email="admin-outsider-requirements@example.com"
    )
    foreign = await async_client.get(f"{BASE}/{created['id']}", headers=outsider)
    assert foreign.status_code == 404, foreign.text
    foreign_retire = await async_client.post(f"{BASE}/{created['id']}/retire", headers=outsider)
    assert foreign_retire.status_code == 404, foreign_retire.text
    still = (await async_client.get(f"{BASE}/{created['id']}", headers=headers)).json()
    assert still["status"] == "active"


@pytest.mark.anyio
async def test_центр_внимания_показывает_просроченное_админу_и_ответственному(
    async_client: AsyncClient, make_auth_headers, sessionmaker
) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)
    owner_headers = await make_auth_headers(
        RoleEnum.WORKER, email="owner-worker-requirements@example.com"
    )
    other_headers = await make_auth_headers(
        RoleEnum.WORKER, email="other-worker-requirements@example.com"
    )
    owner_id = await _user_id(sessionmaker, "owner-worker-requirements@example.com")

    overdue_critical = await _create(
        async_client,
        headers,
        severity="critical",
        next_due_at=PAST.isoformat(),
        owner_user_id=owner_id,
    )
    overdue_high = await _create(
        async_client, headers, severity="medium", next_due_at=PAST.isoformat()
    )
    calm = await _create(async_client, headers, next_due_at=FAR_FUTURE.isoformat())
    assert overdue_critical["owner_name"]

    attention = (await async_client.get(ATTENTION, headers=headers)).json()
    (critical_item,) = _requirement_items(attention, overdue_critical["id"])
    assert critical_item["severity"] == "critical"
    assert critical_item["status"] == "overdue"
    assert critical_item["reason"] == "Контрольная дата прошла"
    assert critical_item["title"].startswith(f"Требование {overdue_critical['code']}:")
    (high_item,) = _requirement_items(attention, overdue_high["id"])
    assert high_item["severity"] == "high"
    assert _requirement_items(attention, calm["id"]) == []
    assert attention["summary"]["overdue_requirements"] == 2
    assert any("просроченные требования" in rec for rec in attention["recommendations"])

    # Ответственный без обзора по арендатору видит своё — и только своё.
    attention = (await async_client.get(ATTENTION, headers=owner_headers)).json()
    assert len(_requirement_items(attention, overdue_critical["id"])) == 1
    assert _requirement_items(attention, overdue_high["id"]) == []
    assert attention["summary"]["overdue_requirements"] == 1
    listing = (await async_client.get(BASE, headers=owner_headers)).json()
    assert [item["id"] for item in listing["items"]] == [overdue_critical["id"]]
    own = await async_client.get(f"{BASE}/{overdue_critical['id']}", headers=owner_headers)
    assert own.status_code == 200, own.text

    attention = (await async_client.get(ATTENTION, headers=other_headers)).json()
    assert _requirement_items(attention, overdue_critical["id"]) == []
    assert attention["summary"]["overdue_requirements"] == 0

    # Подтверждение исполнения убирает запись из Центра внимания.
    closed = await async_client.post(
        f"{BASE}/{overdue_critical['id']}/evidence", json={"note": "Сделано"}, headers=headers
    )
    assert closed.status_code == 201, closed.text
    attention = (await async_client.get(ATTENTION, headers=headers)).json()
    assert _requirement_items(attention, overdue_critical["id"]) == []
    assert attention["summary"]["overdue_requirements"] == 1


@pytest.mark.anyio
async def test_справочник_формы_открыт_специалисту_а_роль_и_площадка_проверяются(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory
) -> None:
    """Срез-147: витрина 19.2 доводится до роли, которая реестр ведёт.

    Специалист по ОТ заводит требования, но административные справочники
    (пользователи, площадки) ему закрыты — ответственного было не выбрать,
    площадку — не привязать. Своя ручка отдаёт только нужное для выбора;
    роль — закрытый словарь; снесённая площадка не привязывается.
    """
    specialist = await make_auth_headers(RoleEnum.OT_SPECIALIST)
    worker = await make_auth_headers(
        RoleEnum.WORKER, email="candidate-worker-requirements@example.com"
    )
    worker_id = await _user_id(sessionmaker, "candidate-worker-requirements@example.com")

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(
            tenant=tenant, name="АКМЕ Требования", session=session
        )
        site = Site(tenant_id=tenant.id, company_id=company.id, name="Цех требований")
        gone = Site(
            tenant_id=tenant.id,
            company_id=company.id,
            name="Снесённый цех",
            deleted_at=datetime.now(tz=timezone.utc),
        )
        session.add_all([site, gone])
        await session.flush()
        site_id, gone_id = site.id, gone.id
        await session.commit()

    # Почему нужна своя ручка: административные справочники специалисту закрыты.
    assert (await async_client.get("/api/v1/admin/users", headers=specialist)).status_code == 403
    # Срез-217: площадки открыты профильным ролям по карте прав экрана; отрицательный
    # контроль — ручка, оставшаяся только у администратора.
    assert (
        await async_client.get("/api/v1/admin/tenant-health", headers=specialist)
    ).status_code == 403

    response = await async_client.get(f"{BASE}/options", headers=specialist)
    assert response.status_code == 200, response.text
    options = response.json()
    owners = {item["id"]: item for item in options["owners"]}
    assert owners[worker_id]["role"] == "worker"
    assert owners[worker_id]["role_label"] == "Рабочий / сотрудник"
    assert owners[worker_id]["name"]
    # Ровно то, что нужно для выбора: без почты, атрибутов и прав.
    assert set(owners[worker_id]) == {"id", "name", "role", "role_label"}
    sites = {item["id"]: item for item in options["sites"]}
    assert sites[site_id] == {
        "id": site_id,
        "name": "Цех требований",
        "company_name": "АКМЕ Требования",
    }
    assert gone_id not in sites
    roles = {item["code"]: item["label"] for item in options["roles"]}
    assert roles["ot_specialist"] == "Специалист ОТ"
    # Псевдонимы ролей человеку не предлагаются — две одинаковые строки в списке.
    assert "employee" not in roles and "inspector_contractor" not in roles
    assert set(roles) <= {role.value for role in RoleEnum}

    # Работник требований не заводит — и справочник ему ни к чему.
    forbidden = await async_client.get(f"{BASE}/options", headers=worker)
    assert forbidden.status_code == 403, forbidden.text

    # Роль — закрытый словарь: выдуманная отвергается словами и в базу не ложится.
    bad_role = await async_client.post(
        BASE,
        json={"code": f"R-{uuid4().hex[:4]}", "title": "К начальнику", "role_code": "boss"},
        headers=specialist,
    )
    assert bad_role.status_code == 422, bad_role.text
    assert "boss" in bad_role.text

    created = await _create(
        async_client,
        specialist,
        site_id=site_id,
        owner_user_id=worker_id,
        role_code="worker",
        next_due_at=FAR_FUTURE.isoformat(),
    )
    assert created["site_name"] == "Цех требований"
    assert created["owner_user_id"] == worker_id
    assert created["role_label"] == "Рабочий / сотрудник"
    listing = (await async_client.get(BASE, headers=specialist)).json()
    (item,) = [row for row in listing["items"] if row["id"] == created["id"]]
    assert item["site_name"] == "Цех требований"

    # Правка перевешивает роль, снимает площадку и ответственного.
    patched = await async_client.patch(
        f"{BASE}/{created['id']}",
        json={"site_id": None, "owner_user_id": None, "role_code": "line_manager"},
        headers=specialist,
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["site_id"] is None
    assert patched.json()["site_name"] is None
    assert patched.json()["owner_name"] is None
    assert patched.json()["role_label"] == "Линейный руководитель"

    # Снесённая площадка существует в базе, но привязать её нельзя — 404, как чужую.
    dead_site = await async_client.patch(
        f"{BASE}/{created['id']}", json={"site_id": gone_id}, headers=specialist
    )
    assert dead_site.status_code == 404, dead_site.text
