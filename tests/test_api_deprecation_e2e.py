"""OPS-73 (разд. 73.2): заголовки устаревания на ЖИВОМ приложении.

Юнит-тесты middleware ходят по искусственному Starlette-приложению; здесь —
проверка проводки в настоящем: реестр `core/api_deprecation.py` содержит
`/api/v1/files-legacy`, middleware зарегистрирована в `create_app`, и реальный
ответ реального legacy-роутера обязан несть Sunset. Без этого теста реестр и
middleware могли бы существовать порознь и оба выглядеть работающими.
"""

from __future__ import annotations

import pytest

API = "/api/v1"


@pytest.mark.anyio
class TestDeprecationOnRealApp:
    async def test_legacy_files_response_carries_sunset(
        self, async_client, make_auth_headers
    ) -> None:
        from app.models.models import RoleEnum

        headers = await make_auth_headers(RoleEnum.ADMIN)

        # Любой ответ поверхности годится, включая 404 по несуществующему id:
        # предупреждение обязано стоять и на ошибках.
        response = await async_client.get(
            f"{API}/files-legacy/00000000-0000-0000-0000-000000000000", headers=headers
        )

        assert (
            "sunset" in response.headers
        ), "ответ /api/v1/files-legacy не несёт Sunset: реестр и middleware разошлись"
        assert "deprecation" in response.headers
        assert 'rel="successor-version"' in response.headers.get("link", "")

    async def test_modern_files_route_is_clean(self, async_client, make_auth_headers) -> None:
        from app.models.models import RoleEnum

        headers = await make_auth_headers(RoleEnum.ADMIN)

        response = await async_client.get(
            f"{API}/files/00000000-0000-0000-0000-000000000000", headers=headers
        )

        assert "sunset" not in response.headers
        assert "deprecation" not in response.headers
