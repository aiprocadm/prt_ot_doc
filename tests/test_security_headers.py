"""SEC-64 (разд. 64.1): заголовки безопасности на уровне приложения.

ТЗ называет их дважды — «XSS → CSP-заголовки» и «Security Misconfiguration →
Secure headers». В репозитории они стояли только в ``proxy/nginx.conf``, а конфиг
живого стенда не ставил ни одного, поэтому на реальном развёртывании их не было.

Ставить их в приложении принципиально: прокси меняются (nginx, Traefik, облачный
балансировщик, прямой доступ в dev), и защита, живущая в одном из них, отсутствует
во всех остальных.
"""

from __future__ import annotations

import pytest

API_PREFIX = "/api/v1"

_EXPECTED = {
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "no-referrer",
    "cross-origin-opener-policy": "same-origin",
    "cross-origin-resource-policy": "same-origin",
}


@pytest.mark.anyio
async def test_security_headers_present_on_success(async_client, make_auth_headers) -> None:
    response = await async_client.get(f"{API_PREFIX}/companies", headers=await make_auth_headers())
    assert response.status_code == 200, response.text

    for name, value in _EXPECTED.items():
        assert response.headers.get(name) == value, name
    assert "default-src 'none'" in response.headers.get("content-security-policy", "")
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]


@pytest.mark.anyio
async def test_security_headers_present_on_error_responses(async_client) -> None:
    """Ответы обработчиков ошибок — тоже ответы: без заголовков они уязвимы так же."""

    # Без заголовка тенанта запрос отбивает TenantMiddleware (400 TENANT_REQUIRED) —
    # конкретный код неважен, важно, что это ответ, сформированный НЕ обработчиком
    # маршрута, и заголовки на нём всё равно есть.
    response = await async_client.get(f"{API_PREFIX}/companies")
    assert response.status_code >= 400, response.text
    assert response.headers.get("x-content-type-options") == "nosniff"
    assert "content-security-policy" in response.headers


@pytest.mark.anyio
async def test_security_headers_present_on_unrouted_path(async_client) -> None:
    response = await async_client.get(f"{API_PREFIX}/definitely-not-a-route")
    assert response.status_code >= 400
    assert response.headers.get("x-frame-options") == "DENY"


@pytest.mark.anyio
async def test_hsts_is_absent_outside_production(async_client) -> None:
    """За TLS-терминирующим прокси приложение видит http: HSTS из dev-запуска
    закрепил бы в браузере разработчика https-редирект на localhost."""

    response = await async_client.get(f"{API_PREFIX}/definitely-not-a-route")
    assert "strict-transport-security" not in response.headers


def test_hsts_emitted_for_production_settings() -> None:
    from app.middleware.security_headers import SecurityHeadersMiddleware

    middleware = SecurityHeadersMiddleware(app=None, hsts_max_age=31_536_000)
    headers = dict(middleware._headers_for("/api/v1/companies"))
    assert headers[b"strict-transport-security"] == b"max-age=31536000; includeSubDomains"


def test_csp_skipped_for_docs_paths() -> None:
    """Swagger UI тянет ассеты с CDN — строгая CSP его ломает."""

    from app.middleware.security_headers import SecurityHeadersMiddleware

    middleware = SecurityHeadersMiddleware(app=None, exempt_path_prefixes=("/api/docs",))

    on_docs = dict(middleware._headers_for("/api/docs"))
    assert b"content-security-policy" not in on_docs
    # ...а остальные заголовки на документации остаются.
    assert on_docs[b"x-frame-options"] == b"DENY"

    on_api = dict(middleware._headers_for("/api/v1/companies"))
    assert b"content-security-policy" in on_api


def test_existing_response_headers_are_not_overwritten() -> None:
    """У отдельного ответа может быть осознанно другая политика (например, файл)."""

    import asyncio

    from app.middleware.security_headers import SecurityHeadersMiddleware

    captured: list[dict] = []

    async def _app(scope, receive, send):
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"x-frame-options", b"SAMEORIGIN")],
            }
        )

    async def _send(message):
        captured.append(message)

    middleware = SecurityHeadersMiddleware(app=_app)
    asyncio.run(middleware({"type": "http", "path": "/x"}, None, _send))

    headers = captured[0]["headers"]
    frame_values = [value for name, value in headers if name == b"x-frame-options"]
    assert frame_values == [b"SAMEORIGIN"], "middleware не должен дублировать/перетирать"


def test_non_http_scope_passes_through() -> None:
    import asyncio

    from app.middleware.security_headers import SecurityHeadersMiddleware

    seen: list[str] = []

    async def _app(scope, receive, send):
        seen.append(scope["type"])

    middleware = SecurityHeadersMiddleware(app=_app)
    asyncio.run(middleware({"type": "websocket"}, None, None))
    assert seen == ["websocket"]
