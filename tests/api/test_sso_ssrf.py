"""Единый вход не ходит в закрытую сеть (SEC-64 §64.3, срез-206).

Адреса провайдера задаёт АДМИНИСТРАТОР ЗАКАЗЧИКА — значит, это такая же
исходящая интеграция, как вебхук, и подчиняется тому же правилу. В срезе-204
проверки здесь не было: администратор мог указать внутренний адрес и заставить
платформу ходить в закрытую сеть.

Проверка стоит ДВАЖДЫ, и это не перестраховка:

* **на записи** — чтобы отказ пришёл сразу и понятным словом;
* **перед самим вызовом** — потому что между сохранением настройки и входом имя
  может переехать на внутренний адрес. Одной проверки на записи мало.

ЗАПУСК: ``PYTHONPATH=backend pytest tests/api/test_sso_ssrf.py -v``.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.core.config import get_settings
from app.models.models import RoleEnum

SETTINGS = "/api/v1/settings/sso"
ISSUER = "https://login.acme-test.ru"


@pytest.fixture(autouse=True)
def _strict_env(monkeypatch: pytest.MonkeyPatch):
    # APP_ENV НЕ переключаем на staging: он тянет за собой обязательную пару
    # ключей RSA и валит запуск настроек (известная грабля публикации). Это не
    # ослабляет проверку: в мягком режиме сторож всё равно отвергает
    # БУКВАЛЬНЫЕ приватные адреса, а здесь проверяются именно они — имена он
    # не резолвит только затем, чтобы тесты не ходили в сеть.
    monkeypatch.setenv("WEBHOOK_SSRF_GUARD_ENABLED", "1")
    monkeypatch.setenv("SSO_REDIRECT_URI", "https://app.example.com/api/v1/auth/sso/callback")
    monkeypatch.setenv("ACME_TEST_SSO_SECRET", "super-secret")
    get_settings.cache_clear()  # type: ignore[attr-defined]
    yield
    get_settings.cache_clear()  # type: ignore[attr-defined]


def _payload(**overrides) -> dict:
    payload = {
        "provider": "oidc",
        "issuer": ISSUER,
        "client_id": "ptd-client",
        "client_secret_env": "ACME_TEST_SSO_SECRET",
        "authorization_endpoint": f"{ISSUER}/authorize",
        "token_endpoint": f"{ISSUER}/token",
        "jwks_uri": f"{ISSUER}/jwks",
        "email_domains": ["acme-test.ru"],
        "jit_enabled": False,
        "default_role": "worker",
    }
    payload.update(overrides)
    return payload


@pytest.mark.anyio
@pytest.mark.parametrize(
    "field",
    ["token_endpoint", "jwks_uri", "authorization_endpoint"],
)
@pytest.mark.parametrize(
    "unsafe",
    [
        "https://127.0.0.1/token",
        "https://10.0.0.5/token",
        "https://169.254.169.254/latest/meta-data/",
        "https://[::1]/token",
    ],
)
async def test_внутренний_адрес_провайдера_не_сохраняется(
    async_client: AsyncClient, make_auth_headers, field: str, unsafe: str
) -> None:
    """169.254.169.254 — служба метаданных облака: оттуда достают ключи доступа
    к самой инфраструктуре. Поэтому проверяются не только «локальные» адреса."""

    headers = await make_auth_headers(RoleEnum.ADMIN)

    response = await async_client.put(SETTINGS, json=_payload(**{field: unsafe}), headers=headers)

    assert response.status_code == 422, response.text
    assert "недопустим" in response.json().get("message", response.text)


@pytest.mark.anyio
async def test_обычный_адрес_сохраняется(async_client: AsyncClient, make_auth_headers) -> None:
    """Сторож не должен запрещать лишнего: иначе его выключат целиком."""

    headers = await make_auth_headers(RoleEnum.ADMIN)

    response = await async_client.put(SETTINGS, json=_payload(), headers=headers)

    assert response.status_code == 200, response.text


@pytest.mark.anyio
async def test_выключенный_провайдер_адреса_не_проверяет(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """Выключая единый вход, администратор не обязан сначала чинить адреса,
    которые всё равно перестанут использоваться."""

    headers = await make_auth_headers(RoleEnum.ADMIN)

    response = await async_client.put(
        SETTINGS,
        json=_payload(provider="disabled", token_endpoint="https://127.0.0.1/token"),
        headers=headers,
    )

    assert response.status_code == 200, response.text
