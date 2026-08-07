"""OPS-72 срез-4 (разд. 72.3): grace-период — данные только на чтение.

ТЗ: «после расторжения данные хранятся N дней **(read-only)** на случай возврата
или споров». Смысл периода — зафиксировать состояние; если данные всё это время
меняются, спорить будут о том, чего уже нет.

Что закрепляется:

* чтение работает, запись отклоняется с датой окончания режима (отказ без даты
  читается как поломка и порождает обращение в поддержку);
* **отмена расторжения возможна изнутри режима** — иначе режим запирает выход
  из себя, и вернувшийся клиент не может вернуться;
* **вход в систему возможен** — логин это POST, и без исключения «только
  чтение» превратилось бы в «нет доступа», то есть клиент не смог бы забрать
  свои данные;
* после отмены запись работает СРАЗУ: кэша, из-за которого клиент ждал бы, нет;
* **чужой арендатор не задет** — расторжение одного не должно останавливать
  работу соседа.
"""

from __future__ import annotations

import pytest

from app.middleware.offboarding_readonly import READ_ONLY_ERROR_CODE
from app.models.models import RoleEnum

API_PREFIX = "/api/v1"


async def _start_grace(async_client, headers, *, grace_days: int = 30) -> None:
    response = await async_client.post(
        f"{API_PREFIX}/offboarding/request",
        json={"reason": "переезд", "grace_days": grace_days},
        headers=headers,
    )
    assert response.status_code == 201, response.text


@pytest.mark.anyio
class TestGraceReadOnly:
    async def test_write_is_rejected_during_grace(self, async_client, make_auth_headers) -> None:
        headers = await make_auth_headers(RoleEnum.ADMIN)
        await _start_grace(async_client, headers)

        response = await async_client.post(
            f"{API_PREFIX}/companies",
            json={"name": "Новая компания"},
            headers=headers,
        )

        assert response.status_code == 409, response.text
        detail = response.json()["detail"]
        assert detail["code"] == READ_ONLY_ERROR_CODE
        # Дата окончания обязана быть в ответе: «запрещено» без срока читается
        # как поломка.
        assert detail["grace_until"]

    async def test_read_still_works_during_grace(self, async_client, make_auth_headers) -> None:
        headers = await make_auth_headers(RoleEnum.ADMIN)
        await _start_grace(async_client, headers)

        response = await async_client.get(f"{API_PREFIX}/companies", headers=headers)

        assert response.status_code == 200, response.text

    async def test_cancelling_the_offboarding_is_possible_from_inside_the_mode(
        self, async_client, make_auth_headers
    ) -> None:
        """Режим не должен запирать выход из себя."""

        headers = await make_auth_headers(RoleEnum.ADMIN)
        await _start_grace(async_client, headers)

        cancelled = await async_client.post(
            f"{API_PREFIX}/offboarding/cancel", json={"reason": "остаёмся"}, headers=headers
        )
        assert cancelled.status_code == 200, cancelled.text

        # После отмены запись работает СРАЗУ — без окна ожидания кэша.
        created = await async_client.post(
            f"{API_PREFIX}/companies", json={"name": "Снова работаем"}, headers=headers
        )
        assert created.status_code in (200, 201), created.text

    async def test_login_still_works_during_grace(
        self, async_client, make_auth_headers, data_factory, sessionmaker
    ) -> None:
        """Логин — POST. Без исключения клиент не вошёл бы забрать свои данные."""

        headers = await make_auth_headers(RoleEnum.ADMIN)
        async with sessionmaker() as session:
            tenant = await data_factory.ensure_tenant(slug="test", session=session)
            await data_factory.create_user(
                tenant=tenant,
                session=session,
                email="leaving@example.com",
                password="secret123",
                role=RoleEnum.ADMIN,
            )
            await session.commit()
        await _start_grace(async_client, headers)

        response = await async_client.post(
            f"{API_PREFIX}/auth/login",
            json={"email": "leaving@example.com", "password": "secret123"},
            headers={"X-Tenant": "test"},
        )

        assert response.status_code != 409, response.text

    async def test_export_still_works_during_grace(self, async_client, make_auth_headers) -> None:
        """Забрать данные — ровно то, ради чего grace-период и существует."""

        headers = await make_auth_headers(RoleEnum.ADMIN)
        await _start_grace(async_client, headers)

        response = await async_client.get(
            f"{API_PREFIX}/offboarding/export/manifest", headers=headers
        )
        assert response.status_code == 200, response.text

    async def test_another_tenant_is_not_frozen(self, async_client, make_auth_headers) -> None:
        """Расторжение одного арендатора не останавливает работу соседа."""

        leaving = await make_auth_headers(RoleEnum.ADMIN)
        staying = await make_auth_headers(
            RoleEnum.ADMIN, tenant="acme", email="admin-acme@example.com"
        )
        await _start_grace(async_client, leaving)

        response = await async_client.post(
            f"{API_PREFIX}/companies", json={"name": "Сосед работает"}, headers=staying
        )

        assert response.status_code in (200, 201), response.text
