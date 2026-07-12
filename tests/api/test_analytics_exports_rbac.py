"""RBAC guards for the /analytics and /exports routers + route registration hygiene.

Сверка 2026-07-10 нашла два независимых дефекта:

* /analytics (11 dashboard + 6 trends + POST /recompute) и /exports не имели
  ролевой защиты — только get_session + get_tenant_record, т.е. управленческие
  KPI и export-центр были доступны любому аутентифицированному пользователю
  тенанта. Здесь фиксируем контракт: 403 для запрещённой роли, 200/201 для
  разрешённой (паттерн — tests/test_rbac_abac.py).
* operational_dashboard.router регистрировался дважды в
  backend/app/api/v1/route_groups.py (с prefix="" и без prefix) — маршрут
  должен быть зарегистрирован ровно один раз и оставаться доступным.
"""

from __future__ import annotations

import pytest
from fastapi.routing import APIRoute

from app.models.models import RoleEnum


@pytest.mark.anyio
async def test_analytics_dashboard_forbidden_for_worker(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.WORKER)

    response = await async_client.get("/api/v1/analytics/dashboard/safety", headers=headers)

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


@pytest.mark.anyio
async def test_analytics_dashboard_allowed_for_line_manager(
    async_client, make_auth_headers
) -> None:
    headers = await make_auth_headers(RoleEnum.LINE_MANAGER)

    response = await async_client.get("/api/v1/analytics/dashboard/safety", headers=headers)

    assert response.status_code == 200


@pytest.mark.anyio
async def test_analytics_trends_forbidden_for_worker(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.WORKER)

    response = await async_client.get("/api/v1/analytics/trends/incidents", headers=headers)

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


@pytest.mark.anyio
async def test_analytics_trends_allowed_for_ot_specialist(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.OT_SPECIALIST)

    response = await async_client.get("/api/v1/analytics/trends/incidents", headers=headers)

    assert response.status_code == 200


@pytest.mark.anyio
async def test_analytics_recompute_forbidden_for_read_only_role(
    async_client, make_auth_headers
) -> None:
    """line_manager может читать дашборды, но не пересчитывать снапшоты."""
    headers = await make_auth_headers(RoleEnum.LINE_MANAGER)

    response = await async_client.post("/api/v1/analytics/recompute", headers=headers)

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


@pytest.mark.anyio
async def test_analytics_recompute_allowed_for_admin(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)

    response = await async_client.post("/api/v1/analytics/recompute", headers=headers)

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.anyio
async def test_exports_list_forbidden_for_worker(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.WORKER)

    response = await async_client.get("/api/v1/exports", headers=headers)

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


@pytest.mark.anyio
async def test_exports_list_allowed_for_ot_specialist(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.OT_SPECIALIST)

    response = await async_client.get("/api/v1/exports", headers=headers)

    assert response.status_code == 200


@pytest.mark.anyio
async def test_exports_create_forbidden_for_read_only_role(async_client, make_auth_headers) -> None:
    """line_manager может читать export-центр, но не создавать job'ы."""
    headers = await make_auth_headers(RoleEnum.LINE_MANAGER)

    response = await async_client.post(
        "/api/v1/exports",
        json={"export_type": "training_matrix", "scope_json": {"scope": "tenant"}},
        headers=headers,
    )

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"


@pytest.mark.anyio
async def test_exports_create_allowed_for_ot_specialist(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.OT_SPECIALIST)

    response = await async_client.post(
        "/api/v1/exports",
        json={"export_type": "training_matrix", "scope_json": {"scope": "tenant"}},
        headers=headers,
    )

    assert response.status_code == 201


@pytest.mark.anyio
async def test_operational_dashboard_registered_once(app_fixture) -> None:
    routes = [
        route
        for route in app_fixture.routes
        if isinstance(route, APIRoute) and route.path.endswith("/operational/dashboard")
    ]

    assert len(routes) == 1, f"expected single registration, got {len(routes)}"


@pytest.mark.anyio
async def test_operational_dashboard_still_available(async_client, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)

    response = await async_client.get("/api/v1/operational/dashboard", headers=headers)

    assert response.status_code == 200
