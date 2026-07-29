"""SEC-64 (разд. 64.1, строка CSRF): проверка Origin для cookie-аутентификации.

Вердикт «CSRF неприменим, у нас Bearer» был бы неверным: у ``POST /auth/refresh``
refresh-токен берётся из **cookie** — это единственная мутация, которую браузер
может выполнить, не имея доступа к токену.

Что здесь закрепляется:

* cookie-запрос с чужого Origin отвергается (403), даже если сам токен валиден;
* cookie-запрос со СВОЕГО Origin проходит;
* запрос **с токеном в теле** (серверный клиент) Origin не требует — иначе гард
  сломал бы интеграции, ничего не добавив: Bearer/тело кросс-сайтом не подделать;
* открытый CORS (`*`) обессмысливает проверку, и она не притворяется работающей.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.csrf import CsrfOriginError, assert_trusted_origin, is_origin_allowed

ALLOWED = ["http://localhost:5173", "https://app.example.com"]


def _request(headers: dict[str, str]) -> SimpleNamespace:
    return SimpleNamespace(headers={k.lower(): v for k, v in headers.items()})


def _settings(allowed=None) -> SimpleNamespace:
    return SimpleNamespace(allowed_origins=ALLOWED if allowed is None else allowed)


@pytest.mark.parametrize(
    ("candidate", "expected"),
    [
        ("http://localhost:5173", True),
        ("https://app.example.com", True),
        # Путь и хвост не должны влиять: сравнивается источник, а не URL.
        ("https://app.example.com/login?x=1", True),
        ("HTTPS://APP.EXAMPLE.COM", True),
        ("https://evil.example.com", False),
        # Похожий, но другой хост — классическая ошибка «сравнили подстрокой».
        ("https://app.example.com.evil.tld", False),
        ("http://app.example.com", False),  # другая схема
        ("https://app.example.com:8443", False),  # другой порт
        ("", False),
        ("not-a-url", False),
    ],
)
def test_origin_matching(candidate: str, expected: bool) -> None:
    assert is_origin_allowed(candidate, ALLOWED) is expected


def test_allowed_origin_passes() -> None:
    assert_trusted_origin(
        _request({"Origin": "https://app.example.com"}), settings=_settings()
    )


def test_foreign_origin_is_rejected() -> None:
    with pytest.raises(CsrfOriginError) as excinfo:
        assert_trusted_origin(
            _request({"Origin": "https://evil.example.com"}), settings=_settings()
        )
    assert excinfo.value.status_code == 403
    assert excinfo.value.detail["code"] == "CSRF_ORIGIN_REJECTED"


def test_referer_is_accepted_as_a_fallback() -> None:
    assert_trusted_origin(
        _request({"Referer": "https://app.example.com/app/login"}), settings=_settings()
    )


def test_foreign_referer_is_rejected() -> None:
    with pytest.raises(CsrfOriginError):
        assert_trusted_origin(
            _request({"Referer": "https://evil.example.com/x"}), settings=_settings()
        )


def test_missing_origin_is_rejected() -> None:
    """Современные браузеры шлют Origin на всех небезопасных методах, включая
    same-origin, поэтому его отсутствие у cookie-запроса — аномалия."""

    with pytest.raises(CsrfOriginError) as excinfo:
        assert_trusted_origin(_request({}), settings=_settings())
    assert "Origin" in excinfo.value.detail["message"]


def test_wildcard_cors_disables_the_check() -> None:
    """При открытом CORS проверка бессмысленна — и не притворяется работающей."""

    assert_trusted_origin(
        _request({"Origin": "https://evil.example.com"}), settings=_settings(["*"])
    )


@pytest.mark.anyio
class TestRefreshEndpointCsrf:
    async def test_cookie_refresh_from_foreign_origin_is_rejected(
        self, async_client, make_auth_headers
    ) -> None:
        from app.api.routes.auth import REFRESH_COOKIE_NAME

        headers = {**await make_auth_headers(), "Origin": "https://evil.example.com"}
        response = await async_client.post(
            "/api/v1/auth/refresh",
            headers=headers,
            cookies={REFRESH_COOKIE_NAME: "any-token-value"},
        )
        assert response.status_code == 403, response.text
        assert "CSRF_ORIGIN_REJECTED" in response.text

    async def test_body_refresh_does_not_require_origin(
        self, async_client, make_auth_headers
    ) -> None:
        """Серверный клиент Origin не шлёт — гард не должен ломать интеграции."""

        response = await async_client.post(
            "/api/v1/auth/refresh",
            headers=await make_auth_headers(),
            json={"refresh_token": "obviously-invalid"},
        )
        # 401 (токен невалиден), а НЕ 403 (не отвергнут по Origin).
        assert response.status_code == 401, response.text
