"""BIZ-49 срез-6: `/managed-clients/my` должен работать по обычному токену.

**Регресс живого дефекта.** Роут задумывался «без роли-гейта портфеля», и
зависимость доступа у него не стояла вовсе. Но ``get_auth_ctx`` только ЧИТАЕТ
контекст, который кладёт зависимость доступа, — поэтому с валидным токеном роут
отвечал 401. Юнит-тесты этого не поймали: они зовут обработчик напрямую, минуя
цепочку зависимостей. Проверка через настоящий HTTP-клиент — единственная,
которая ловит такой разрыв.

Ожидание: **404** (модуль по умолчанию выключен), а НЕ 401. Именно 404
доказывает, что аутентификация прошла и запрос дошёл до проверки модуля.
"""

from __future__ import annotations

import pytest

from app.models.models import RoleEnum

API_PREFIX = "/api/v1"


@pytest.mark.anyio
async def test_my_clients_authenticates_with_a_normal_token(
    async_client, make_auth_headers
) -> None:
    headers = await make_auth_headers(RoleEnum.OT_SPECIALIST)
    response = await async_client.get(f"{API_PREFIX}/managed-clients/my", headers=headers)

    assert response.status_code != 401, "валидный токен не должен давать 401"
    assert response.status_code == 404
    assert response.json()["code"] == "MANAGED_CLIENTS_DISABLED"


@pytest.mark.anyio
async def test_my_clients_without_token_is_rejected(async_client, make_auth_headers) -> None:
    """Без токена — отказ. Берём арендатора из валидных заголовков и убираем
    только Authorization: иначе раньше сработает проверка арендатора (400),
    и тест проверял бы не то, что заявлено."""

    headers = await make_auth_headers(RoleEnum.OT_SPECIALIST)
    headers.pop("Authorization", None)
    response = await async_client.get(f"{API_PREFIX}/managed-clients/my", headers=headers)

    assert response.status_code == 401
