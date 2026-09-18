from __future__ import annotations

import pytest

from app.models.models import RoleEnum
from app.modules.projections.models import ExportJob, PackageReadModel, SearchIndexEntry


@pytest.mark.anyio
async def test_analytics_and_trends_endpoints(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    async with sessionmaker() as session:  # type: AsyncSession
        tenant = await data_factory.ensure_tenant(session=session)
        session.add(PackageReadModel(tenant_id=tenant.id, package_id="pkg-1", status="in_progress"))
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN)
    response = await async_client.get(
        "/api/v1/analytics/dashboard/executive", headers={**headers, "X-Tenant": "test"}
    )
    assert response.status_code == 200
    assert "dashboard" in response.json()

    trend = await async_client.get(
        "/api/v1/analytics/trends/incidents", headers={**headers, "X-Tenant": "test"}
    )
    assert trend.status_code == 200
    assert trend.json()["metric"] == "incidents"


@pytest.mark.anyio
async def test_search_over_projection_index(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    async with sessionmaker() as session:  # type: AsyncSession
        tenant = await data_factory.ensure_tenant(session=session)
        session.add(
            SearchIndexEntry(
                tenant_id=tenant.id,
                entity_type="person",
                entity_id="person-1",
                title="Иван Иванов",
                route="/persons/person-1",
                search_text="Иван Иванов",
            )
        )
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN)
    response = await async_client.get(
        "/api/v1/search",
        params={"q": "Иван", "entity_types": "person"},
        headers={**headers, "X-Tenant": "test"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["items"]
    assert payload["items"][0]["entity_type"] == "person"


@pytest.mark.anyio
async def test_export_center_idempotent_creation(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    async with sessionmaker() as session:  # type: AsyncSession
        await data_factory.ensure_tenant(session=session)
        await session.commit()

    # RBAC hardening (P10-07 Task 1): /api/v1/exports now requires an
    # authenticated admin/owner/... role, not just an X-Tenant header.
    auth_headers = await make_auth_headers(RoleEnum.ADMIN)
    headers = {**auth_headers, "Idempotency-Key": "same-export"}
    body = {
        "export_type": "training_matrix",
        "scope_json": {"scope": "tenant"},
        "filters_json": {"status": "all"},
    }
    r1 = await async_client.post(
        "/api/v1/exports", json=body, headers={**headers, "X-Tenant": "test"}
    )
    assert r1.status_code == 201
    r2 = await async_client.post(
        "/api/v1/exports", json=body, headers={**headers, "X-Tenant": "test"}
    )
    assert r2.status_code == 201
    assert r1.json()["id"] == r2.json()["id"]

    details = await async_client.get(
        f"/api/v1/exports/{r1.json()['id']}", headers={**auth_headers, "X-Tenant": "test"}
    )
    assert details.status_code == 200


@pytest.mark.anyio
async def test_client_portal_internal_requests_patch(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    async with sessionmaker() as session:  # type: AsyncSession
        await data_factory.ensure_tenant(session=session)
        session.add(
            ExportJob(
                tenant_id=(await data_factory.ensure_tenant(session=session)).id,
                export_type="dummy",
                scope_json={},
                filters_json={},
                status="done",
            )
        )
        await session.commit()

    employee_headers = await make_auth_headers(RoleEnum.EMPLOYEE)

    created = await async_client.post(
        "/api/v1/client-portal/requests",
        json={"title": "Need update", "body": "Please refresh package"},
        headers=employee_headers,
    )
    assert created.status_code == 201
    req_id = created.json()["id"]
    patched = await async_client.patch(
        f"/api/v1/portal-requests/{req_id}",
        json={"status": "in_progress"},
        headers=employee_headers,
    )
    assert patched.status_code == 200
    assert patched.json()["status"] == "in_progress"


@pytest.mark.anyio
async def test_client_user_cannot_patch_internal_portal_requests(async_client, make_auth_headers):
    employee_headers = await make_auth_headers(RoleEnum.EMPLOYEE)
    create_response = await async_client.post(
        "/api/v1/client-portal/requests",
        json={"title": "Need update", "body": "Please refresh package"},
        headers=employee_headers,
    )
    assert create_response.status_code == 201
    req_id = create_response.json()["id"]

    client_headers = await make_auth_headers(RoleEnum.CLIENT_USER)
    patch_response = await async_client.patch(
        f"/api/v1/portal-requests/{req_id}",
        json={"status": "in_progress"},
        headers=client_headers,
    )

    assert patch_response.status_code == 403


@pytest.mark.anyio
async def test_search_returns_extended_facets(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    async with sessionmaker() as session:  # type: AsyncSession
        tenant = await data_factory.ensure_tenant(session=session)
        session.add_all(
            [
                SearchIndexEntry(
                    tenant_id=tenant.id,
                    entity_type="incident",
                    entity_id="incident-1",
                    title="Near miss",
                    status="reported",
                    tags_json={"company_id": "company-1", "site_id": "site-1"},
                    route="/incidents/incident-1",
                    search_text="Near miss reported",
                ),
                SearchIndexEntry(
                    tenant_id=tenant.id,
                    entity_type="incident",
                    entity_id="incident-2",
                    title="Another miss",
                    status="closed",
                    tags_json={"company_id": "company-1", "site_id": "site-2"},
                    route="/incidents/incident-2",
                    search_text="Another miss closed",
                ),
            ]
        )
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN)
    response = await async_client.get(
        "/api/v1/search",
        params={"q": "miss", "entity_types": "incident"},
        headers={**headers, "X-Tenant": "test"},
    )
    assert response.status_code == 200
    facets = response.json()["facets"]
    assert facets["status_counts"]["reported"] == 1
    assert facets["company_counts"]["company-1"] == 2
    assert facets["site_counts"]["site-1"] == 1


@pytest.mark.anyio
async def test_analytics_extended_dashboards(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    async with sessionmaker() as session:  # type: AsyncSession
        tenant = await data_factory.ensure_tenant(session=session)
        session.add(
            PackageReadModel(tenant_id=tenant.id, package_id="pkg-analytics", status="in_progress")
        )
        await session.commit()

    for endpoint in [
        "/api/v1/analytics/dashboard/incidents",
        "/api/v1/analytics/dashboard/inspections",
        "/api/v1/analytics/dashboard/prescriptions",
        "/api/v1/analytics/dashboard/overdue",
        "/api/v1/analytics/dashboard/sla-load",
        "/api/v1/analytics/dashboard/edo",
    ]:
        headers = await make_auth_headers(RoleEnum.ADMIN)
        response = await async_client.get(endpoint, headers={**headers, "X-Tenant": "test"})
        assert response.status_code == 200
        assert "widgets" in response.json()


@pytest.mark.anyio
async def test_search_returns_total_and_extended_filters(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    async with sessionmaker() as session:  # type: AsyncSession
        tenant = await data_factory.ensure_tenant(session=session)
        session.add_all(
            [
                SearchIndexEntry(
                    tenant_id=tenant.id,
                    entity_type="incident",
                    entity_id="incident-prj-1",
                    title="Critical near miss",
                    status="reported",
                    tags_json={
                        "company_id": "company-1",
                        "site_id": "site-1",
                        "project_id": "project-1",
                        "risk_level": "high",
                    },
                    route="/incidents/incident-prj-1",
                    search_text="Critical near miss high risk project one",
                ),
                SearchIndexEntry(
                    tenant_id=tenant.id,
                    entity_type="incident",
                    entity_id="incident-prj-2",
                    title="Near miss archive",
                    status="closed",
                    tags_json={
                        "company_id": "company-1",
                        "site_id": "site-2",
                        "project_id": "project-2",
                        "risk_level": "low",
                    },
                    route="/incidents/incident-prj-2",
                    search_text="Near miss archive low risk project two",
                ),
            ]
        )
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN)
    response = await async_client.get(
        "/api/v1/search",
        params={
            "q": "near miss",
            "entity_types": "incident",
            "project_id": "project-1",
            "risk_level": "high",
        },
        headers={**headers, "X-Tenant": "test"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["entity_id"] == "incident-prj-1"
    assert payload["facets"]["project_counts"]["project-1"] == 1
    assert payload["facets"]["risk_level_counts"]["high"] == 1


@pytest.mark.anyio
async def test_поиск_находит_то_что_человек_открывает_на_экране(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    """Срез-226. Специалист по охране труда — основной пользователь продукта:
    происшествия и проверки он ведёт сам. Поиск обязан их ему отдавать.

    До среза-226 не отдавал. Поиск считал права по словарю
    ``rbac_abac.ROLE_PERMISSIONS``, где СЕМИ настоящих ролей нет вовсе
    (``ot_specialist``, ``ot_pb_lead``, ``ot_head``, ``pb_engineer``,
    ``manager``, ``worker``, ``employee``), зато есть шесть выдуманных. Набор
    прав выходил ПУСТЫМ, и поиск прятал ровно то, что человек открывает на
    экране: замер дал 15 расхождений «экран пускает, а поиск прячет».
    """

    async with sessionmaker() as session:  # type: AsyncSession
        tenant = await data_factory.ensure_tenant(session=session)
        session.add_all(
            [
                SearchIndexEntry(
                    tenant_id=tenant.id,
                    entity_type="incident",
                    entity_id="inc-ot",
                    title="Инцидент: травма на площадке",
                    route="/incidents/inc-ot",
                    search_text="Инцидент травма площадка",
                ),
                SearchIndexEntry(
                    tenant_id=tenant.id,
                    entity_type="inspection",
                    entity_id="insp-ot",
                    title="Проверка ГИТ",
                    route="/inspections/insp-ot",
                    search_text="Проверка ГИТ",
                ),
            ]
        )
        await session.commit()

    params = {"entity_types": "incident,inspection"}
    for role in (RoleEnum.OT_SPECIALIST, RoleEnum.OT_PB_LEAD, RoleEnum.PB_ENGINEER):
        headers = await make_auth_headers(role)
        response = await async_client.get(
            "/api/v1/search", params=params, headers={**headers, "X-Tenant": "test"}
        )
        assert response.status_code == 200, response.text
        kept = {item["entity_type"] for item in response.json()["items"]}
        assert kept == {"incident", "inspection"}, (role.value, sorted(kept))


def test_поиск_не_прячет_того_что_пускает_экран() -> None:
    """Сторож согласия: поиск и экран отвечают на один вопрос одинаково.

    ОБЛАСТЬ ОБЗОРА ВАЖНЕЕ СПИСКА (урок срезов 223–224): проверка идёт по ВСЕМ
    ролям продукта, а не по паре образцов. Пара образцов и была — тест ниже
    брал юриста и администратора, и оба ответа совпадали с прежним поведением,
    поэтому пятнадцать расхождений он не видел.
    """

    from app.core.screen_access import screen_roles
    from app.models.tenant_billing import RoleEnum as ProductRole
    from app.modules.search.api import (
        _SENSITIVE_ENTITY_SCREENS,
        restricted_entity_types_for_roles,
    )

    assert _SENSITIVE_ENTITY_SCREENS, "карта пуста — проверка меряет не то"
    # Экран — независимый источник: роли берутся из единой карты прав, а не
    # из той же функции, что проверяется.
    visible_on_screen = {
        entity_type: set(screen_roles(screen))
        for entity_type, screen in _SENSITIVE_ENTITY_SCREENS.items()
    }
    conflicts: list[str] = []
    seen_hidden = 0
    for role in sorted(item.value for item in ProductRole):
        hidden = restricted_entity_types_for_roles({role})
        seen_hidden += len(hidden)
        for entity_type in sorted(hidden):
            if role in visible_on_screen[entity_type]:
                conflicts.append(f"{role}: экран пускает «{entity_type}», а поиск прячет")
    assert seen_hidden > 0, "разбор не нашёл ни одного скрытого типа — проверка пуста"
    assert not conflicts, "\n".join(conflicts)


def test_карта_поиска_называет_настоящие_права_экрана() -> None:
    """Опечатка в коде права — та же ловушка, что в срезе-224: имя правдоподобно,
    а защиты нет. ``screen_roles`` на неизвестном праве падает, и это нужно
    поймать здесь, а не на живом запросе."""

    from app.core.screen_access import SCREEN_ACCESS
    from app.modules.search.api import _SENSITIVE_ENTITY_SCREENS

    unknown = sorted(set(_SENSITIVE_ENTITY_SCREENS.values()) - set(SCREEN_ACCESS))
    assert not unknown, f"права экрана не заведены: {unknown}"


async def test_search_hides_sensitive_types_from_unprivileged_role(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    """Confidential entity titles (incident/inspection/prescription — these can name
    injured people) must not surface via global search or suggest to a caller lacking
    the domain read permission. Catalog-ish types (person) stay tenant-global."""
    async with sessionmaker() as session:  # type: AsyncSession
        tenant = await data_factory.ensure_tenant(session=session)
        session.add_all(
            [
                SearchIndexEntry(
                    tenant_id=tenant.id,
                    entity_type="incident",
                    entity_id="inc-1",
                    title="Инцидент: травма",
                    route="/incidents/inc-1",
                    search_text="Инцидент травма",
                ),
                SearchIndexEntry(
                    tenant_id=tenant.id,
                    entity_type="person",
                    entity_id="person-1",
                    title="Иван Иванов",
                    route="/persons/person-1",
                    search_text="Иван Иванов",
                ),
            ]
        )
        await session.commit()

    params = {"entity_types": "incident,person"}

    # Lawyer holds documents:* only — no incidents:read → incident hidden, person kept.
    lawyer = await make_auth_headers(RoleEnum.LAWYER)
    resp = await async_client.get(
        "/api/v1/search", params=params, headers={**lawyer, "X-Tenant": "test"}
    )
    assert resp.status_code == 200
    body = resp.json()
    kept_types = {item["entity_type"] for item in body["items"]}
    assert "incident" not in kept_types
    assert "person" in kept_types
    # facet counts must not leak the hidden type either
    assert "incident" not in body["facets"]["type_counts"]

    # /search/suggest is filtered the same way
    suggest = await async_client.get(
        "/api/v1/search/suggest", params={"q": ""}, headers={**lawyer, "X-Tenant": "test"}
    )
    assert suggest.status_code == 200
    assert all(item["entity_type"] != "incident" for item in suggest.json()["items"])

    # Admin (full permission set) still sees the incident.
    admin = await make_auth_headers(RoleEnum.ADMIN)
    resp_admin = await async_client.get(
        "/api/v1/search", params=params, headers={**admin, "X-Tenant": "test"}
    )
    assert resp_admin.status_code == 200
    admin_types = {item["entity_type"] for item in resp_admin.json()["items"]}
    assert {"incident", "person"} <= admin_types
