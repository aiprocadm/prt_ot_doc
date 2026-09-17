"""Единая карта прав экрана — по живым запросам (срез-217).

ЗАЧЕМ. Сторож ``tests/test_menu_matches_api.py`` сравнивает списки ролей. Здесь
проверяется то, ради чего всё делалось: человек с ролью входит и ПОЛУЧАЕТ ответ,
а не 403.

1. Специалист по охране труда — основной пользователь продукта — открывает
   первый экран после входа (сводку главной) и реестр сотрудников. До среза он
   получал отказ на обоих.
2. ``/auth/me/permissions`` отдаёт права экрана в словаре витрины: раньше для
   настоящих ролей список был ПУСТ, и витрина рисовала меню по своей карте.
3. Руководитель службы ОТиПБ — не администратор платформы: правила
   платформы (пользователи, ключи, правила) ему по-прежнему закрыты, хотя всё остальное открыто.
4. Обратная сторона: рабочему выдача СИЗ не открылась — карта не «всем всё».
"""

from __future__ import annotations

import pytest
from fastapi import status
from httpx import AsyncClient

from app.models.models import RoleEnum

pytestmark = pytest.mark.anyio


async def test_специалист_ОТ_открывает_первый_экран(async_client: AsyncClient, make_auth_headers):
    """ГЛАВНОЕ. Все роли приземляются на главную; сводка обязана открываться."""

    headers = await make_auth_headers(RoleEnum.OT_SPECIALIST)

    summary = await async_client.get("/api/v1/dashboard/summary", headers=headers)
    persons = await async_client.get("/api/v1/persons", headers=headers)

    assert summary.status_code == status.HTTP_200_OK, summary.text
    assert persons.status_code == status.HTTP_200_OK, persons.text


async def test_права_экрана_отдаются_в_словаре_витрины(
    async_client: AsyncClient, make_auth_headers
):
    headers = await make_auth_headers(RoleEnum.OT_SPECIALIST)

    response = await async_client.get("/api/v1/auth/me/permissions", headers=headers)

    assert response.status_code == status.HTTP_200_OK, response.text
    granted = set(response.json()["permissions"])
    assert {"dashboard.view", "person.view", "ppe.view", "incident.view"} <= granted
    assert "admin.manage_roles" not in granted


async def test_руководитель_ОТ_не_администратор(async_client: AsyncClient, make_auth_headers):
    """Начальник видит всё, что его специалисты, но настройки платформы — нет."""

    headers = await make_auth_headers(RoleEnum.OT_PB_LEAD)

    persons = await async_client.get("/api/v1/persons", headers=headers)
    # Управление пользователями — не гейтится модулем, поэтому отказ здесь
    # именно ролевой, а не «модуль выключен».
    users = await async_client.get("/api/v1/admin/users", headers=headers)

    assert persons.status_code == status.HTTP_200_OK, persons.text
    assert users.status_code == status.HTTP_403_FORBIDDEN, users.text


async def test_рабочему_выдача_СИЗ_не_открылась(async_client: AsyncClient, make_auth_headers):
    """Обратная сторона: карта расширила ручки до замысла меню, а не до «всем всё»."""

    headers = await make_auth_headers(RoleEnum.WORKER)

    response = await async_client.get("/api/v1/ppe/issues", headers=headers)

    assert response.status_code == status.HTTP_403_FORBIDDEN, response.text


#: Срез-223: ручки ВНЕ меню, где до среза специалист был пущен, а руководитель — нет.
#: Пустое тело: интересует только «не 403» (422 — ручка пустила и не поняла тело).
_WRITE_HANDLES: tuple[tuple[str, str], ...] = (
    ("POST", "/api/v1/notifications/templates"),
    ("POST", "/api/v1/layout-presets"),
    ("POST", "/api/v1/replace-maps"),
    ("POST", "/api/v1/workflow/definitions"),
    ("POST", "/api/v1/pipelines/profiles"),
    ("POST", "/api/v1/package-presets"),
    # report-builder в тестах выключен как модуль (404 всем до ролевого рубежа) —
    # его ролевой рубеж держит сторож по всем ручкам в test_menu_matches_api.py.
    ("POST", "/api/v1/npa"),
    ("POST", "/api/v1/compliance/requirements"),
    ("PATCH", "/api/v1/branding/profile/00000000-0000-0000-0000-000000000001"),
)


@pytest.mark.parametrize("role", [RoleEnum.OT_PB_LEAD, RoleEnum.OT_HEAD])
async def test_руководитель_пишет_там_где_пишет_специалист(
    async_client: AsyncClient, make_auth_headers, role: RoleEnum
):
    """Срез-223: 60 ручек вне меню отказывали руководителю службы ролевым 403."""

    headers = await make_auth_headers(role)
    refused: list[str] = []
    for method, path in _WRITE_HANDLES:
        response = await async_client.request(method, path, headers=headers, json={})
        if response.status_code == status.HTTP_403_FORBIDDEN:
            refused.append(f"{method} {path}: {response.text[:120]}")
    assert not refused, "\n".join(refused)


async def test_рабочему_запись_вне_меню_по_прежнему_закрыта(
    async_client: AsyncClient, make_auth_headers
):
    """Обратная сторона: карта дала руководителям, а не «всем всё»."""

    headers = await make_auth_headers(RoleEnum.WORKER)
    allowed: list[str] = []
    for method, path in _WRITE_HANDLES:
        response = await async_client.request(method, path, headers=headers, json={})
        if response.status_code != status.HTTP_403_FORBIDDEN:
            allowed.append(f"{method} {path}: {response.status_code}")
    assert not allowed, "\n".join(allowed)
