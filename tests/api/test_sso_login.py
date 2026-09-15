"""Единый вход: МЕСТО ПОДКЛЮЧЕНИЯ (BIZ-53 разд. 53.3, срез-204).

Правила проверяются без сети в ``tests/test_sso_rules.py``. Здесь — то, что
урок среза-187 велит проверять отдельно: **тесты шва не заменяют теста места
подключения.** Там десять проверок службы ЭДО были зелёными, а ручка падала
дважды.

Провайдер подменяется транспортом ``httpx``: настоящий корпоративный каталог
для проверки шва не нужен и не должен быть нужен — иначе проверить его можно
было бы только на живом стенде, то есть никогда.

ЗАПУСК: ``PYTHONPATH=backend pytest tests/api/test_sso_login.py -v``.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import AsyncClient
from jose import jwt

from app.core.config import get_settings
from app.models.models import RoleEnum

SSO = "/api/v1/auth/sso"
SETTINGS = "/api/v1/settings/sso"
ISSUER = "https://login.acme-test.ru"
SECRET_ENV = "ACME_TEST_SSO_SECRET"


@pytest.fixture
def idp_key():
    """Ключ «провайдера»: подпись токена личности проверяется по-настоящему."""

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    numbers = key.public_key().public_numbers()

    def b64(value: int) -> str:
        import base64

        raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    jwks = {
        "keys": [
            {
                "kty": "RSA",
                "kid": "idp-1",
                "use": "sig",
                "alg": "RS256",
                "n": b64(numbers.n),
                "e": b64(numbers.e),
            }
        ]
    }
    return private_pem, jwks


def _id_token(private_pem: str, *, audience: str, nonce: str, email: str, verified: bool) -> str:
    now = datetime.now(timezone.utc)
    claims = {
        "iss": ISSUER,
        "aud": audience,
        "sub": "idp-subject-1",
        "email": email,
        "email_verified": verified,
        "name": "Иван Петров",
        "nonce": nonce,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=5)).timestamp()),
    }
    return jwt.encode(claims, private_pem, algorithm="RS256", headers={"kid": "idp-1"})


def _transport(private_pem: str, jwks: dict, *, id_token_factory) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/jwks"):
            return httpx.Response(200, json=jwks)
        if request.url.path.endswith("/token"):
            body = dict(x.split("=", 1) for x in request.content.decode().split("&"))
            return httpx.Response(200, json={"id_token": id_token_factory(body)})
        return httpx.Response(404)

    return httpx.MockTransport(handler)


@pytest.fixture
def stub_provider(monkeypatch, idp_key):
    """Подменяет HTTP-клиент маршрута. Сам маршрут не трогаем."""

    private_pem, jwks = idp_key
    state: dict = {"nonce": "", "email": "ivan@acme-test.ru", "verified": True}

    def install() -> None:
        from app.api.routes import sso as sso_routes

        def factory(body: dict) -> str:
            return _id_token(
                private_pem,
                audience="ptd-client",
                nonce=state["nonce"],
                email=state["email"],
                verified=state["verified"],
            )

        monkeypatch.setattr(
            sso_routes,
            "_http_client",
            lambda: httpx.AsyncClient(
                transport=_transport(private_pem, jwks, id_token_factory=factory)
            ),
        )

    state["install"] = install
    return state


@pytest.fixture(autouse=True)
def _redirect_uri(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SSO_REDIRECT_URI", "https://app.example.com/api/v1/auth/sso/callback")
    monkeypatch.setenv(SECRET_ENV, "super-secret")
    get_settings.cache_clear()  # type: ignore[attr-defined]
    yield
    get_settings.cache_clear()  # type: ignore[attr-defined]


def _config_payload(**overrides) -> dict:
    payload = {
        "provider": "oidc",
        "issuer": ISSUER,
        "client_id": "ptd-client",
        "client_secret_env": SECRET_ENV,
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
async def test_невключённый_вход_честно_отказывает(async_client: AsyncClient) -> None:
    """ГЛАВНОЕ ДЛЯ ЭКРАНА ВХОДА: кнопки нет, а ручка называет причину."""

    status_response = await async_client.get(f"{SSO}/test/status")
    assert status_response.status_code == 200, status_response.text
    assert status_response.json()["enabled"] is False

    start = await async_client.get(f"{SSO}/test/start")
    assert start.status_code == 409, start.text
    assert "не настроен" in start.json().get("message", start.text)


@pytest.mark.anyio
async def test_несуществующий_арендатор_отвечает_как_ненастроенный(
    async_client: AsyncClient,
) -> None:
    """Иначе по этой ручке перебирали бы список заказчиков платформы."""

    response = await async_client.get(f"{SSO}/нет-такого/status")

    assert response.status_code == 200, response.text
    assert response.json()["enabled"] is False


@pytest.mark.anyio
async def test_настройка_пишется_и_читается_без_секрета(
    async_client: AsyncClient, make_auth_headers
) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)

    saved = await async_client.put(SETTINGS, json=_config_payload(), headers=headers)

    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["client_secret_env"] == SECRET_ENV
    # Самого секрета в ответе нет НИ ПОД КАКИМ именем — только признак выдачи.
    assert "super-secret" not in json.dumps(body, ensure_ascii=False)
    assert body["secret_present"] is True


@pytest.mark.anyio
async def test_включённый_вход_виден_экрану(async_client: AsyncClient, make_auth_headers) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)
    await async_client.put(SETTINGS, json=_config_payload(), headers=headers)

    status_response = await async_client.get(f"{SSO}/test/status")
    start = await async_client.get(f"{SSO}/test/start")

    assert status_response.json()["enabled"] is True
    assert start.status_code == 200, start.text
    url = start.json()["authorization_url"]
    assert url.startswith(f"{ISSUER}/authorize?")
    # Обязательные части запроса на месте — иначе провайдер вернёт свою ошибку,
    # и человек увидит чужой экран вместо нашего.
    for part in ("response_type=code", "client_id=ptd-client", "state=", "nonce=", "scope="):
        assert part in url


@pytest.mark.anyio
async def test_настройка_без_доменов_отвергается(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """«Пусто значит всем» — самое дорогое из удобных умолчаний."""

    headers = await make_auth_headers(RoleEnum.ADMIN)

    response = await async_client.put(
        SETTINGS, json=_config_payload(email_domains=[]), headers=headers
    )

    assert response.status_code == 422, response.text


@pytest.mark.anyio
async def test_адреса_провайдера_только_по_https(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """Обмен секретом по HTTP означал бы, что любой на пути его прочитает."""

    headers = await make_auth_headers(RoleEnum.ADMIN)

    response = await async_client.put(
        SETTINGS,
        json=_config_payload(token_endpoint="http://login.acme-test.ru/token"),
        headers=headers,
    )

    assert response.status_code == 422, response.text


@pytest.mark.anyio
async def test_рядовая_роль_не_настраивает_вход(
    async_client: AsyncClient, make_auth_headers
) -> None:
    headers = await make_auth_headers(RoleEnum.WORKER)

    response = await async_client.put(SETTINGS, json=_config_payload(), headers=headers)

    assert response.status_code == 403, response.text


@pytest.mark.anyio
async def test_сотрудник_входит_через_провайдера(
    async_client: AsyncClient, make_auth_headers, stub_provider
) -> None:
    """РАДИ ЧЕГО СРЕЗ: вход корпоративными учётными данными, без второго пароля."""

    headers = await make_auth_headers(RoleEnum.ADMIN)
    me = await async_client.get("/api/v1/auth/me", headers=headers)
    email = me.json()["email"]
    domain = email.rsplit("@", 1)[1]
    await async_client.put(SETTINGS, json=_config_payload(email_domains=[domain]), headers=headers)
    start = await async_client.get(f"{SSO}/test/start")
    url = start.json()["authorization_url"]
    state = url.split("state=")[1].split("&")[0]
    nonce = url.split("nonce=")[1].split("&")[0]
    stub_provider["nonce"] = nonce
    stub_provider["email"] = email
    stub_provider["install"]()

    response = await async_client.get(f"{SSO}/callback", params={"code": "abc", "state": state})

    assert response.status_code == 200, response.text
    assert response.json()["access_token"]
    # Существующего сотрудника не заводим повторно.
    assert response.json()["created"] is False


@pytest.mark.anyio
async def test_чужой_nonce_не_пускает(
    async_client: AsyncClient, make_auth_headers, stub_provider
) -> None:
    """Токен настоящий, но выдан не для ЭТОГО входа: без сверки nonce чужой
    действительный токен того же провайдера пустил бы человека сюда."""

    headers = await make_auth_headers(RoleEnum.ADMIN)
    me = await async_client.get("/api/v1/auth/me", headers=headers)
    email = me.json()["email"]
    await async_client.put(
        SETTINGS,
        json=_config_payload(email_domains=[email.rsplit("@", 1)[1]]),
        headers=headers,
    )
    start = await async_client.get(f"{SSO}/test/start")
    state = start.json()["authorization_url"].split("state=")[1].split("&")[0]
    stub_provider["nonce"] = "совсем-другой-nonce"
    stub_provider["email"] = email
    stub_provider["install"]()

    response = await async_client.get(f"{SSO}/callback", params={"code": "abc", "state": state})

    assert response.status_code == 401, response.text


@pytest.mark.anyio
async def test_неподтверждённая_почта_не_пускает(
    async_client: AsyncClient, make_auth_headers, stub_provider
) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)
    me = await async_client.get("/api/v1/auth/me", headers=headers)
    email = me.json()["email"]
    await async_client.put(
        SETTINGS,
        json=_config_payload(email_domains=[email.rsplit("@", 1)[1]]),
        headers=headers,
    )
    start = await async_client.get(f"{SSO}/test/start")
    url = start.json()["authorization_url"]
    state = url.split("state=")[1].split("&")[0]
    stub_provider["nonce"] = url.split("nonce=")[1].split("&")[0]
    stub_provider["email"] = email
    stub_provider["verified"] = False
    stub_provider["install"]()

    response = await async_client.get(f"{SSO}/callback", params={"code": "abc", "state": state})

    assert response.status_code == 403, response.text
    assert "не подтвердил" in response.json().get("message", response.text)


@pytest.mark.anyio
async def test_чужой_домен_не_пускает(
    async_client: AsyncClient, make_auth_headers, stub_provider
) -> None:
    headers = await make_auth_headers(RoleEnum.ADMIN)
    await async_client.put(SETTINGS, json=_config_payload(), headers=headers)
    start = await async_client.get(f"{SSO}/test/start")
    url = start.json()["authorization_url"]
    state = url.split("state=")[1].split("&")[0]
    stub_provider["nonce"] = url.split("nonce=")[1].split("&")[0]
    stub_provider["email"] = "chuzhoy@other.ru"
    stub_provider["install"]()

    response = await async_client.get(f"{SSO}/callback", params={"code": "abc", "state": state})

    assert response.status_code == 403, response.text
    assert "домен" in response.json().get("message", response.text)


@pytest.mark.anyio
async def test_подделанное_состояние_не_принимается(async_client: AsyncClient) -> None:
    """Состояние подписано нами: чужая строка не пройдёт."""

    response = await async_client.get(
        f"{SSO}/callback", params={"code": "abc", "state": "выдуманное"}
    )

    assert response.status_code == 400, response.text


@pytest.mark.anyio
async def test_обычный_токен_не_годится_как_состояние(
    async_client: AsyncClient, make_auth_headers
) -> None:
    """ТОНКОСТЬ: состояние подписано тем же ключом, что и токены доступа.
    Без проверки вида сюда подошёл бы ЛЮБОЙ наш токен."""

    headers = await make_auth_headers(RoleEnum.ADMIN)
    access = headers["Authorization"].split(" ", 1)[1]

    response = await async_client.get(f"{SSO}/callback", params={"code": "abc", "state": access})

    assert response.status_code == 400, response.text


@pytest.mark.anyio
async def test_токен_подписанный_чужим_ключом_не_пускает(
    async_client: AsyncClient, make_auth_headers, monkeypatch, idp_key
) -> None:
    """ГЛАВНАЯ ПРОВЕРКА БЕЗОПАСНОСТИ СРЕЗА.

    Соблазн «взять claims без проверки, мы же только что сходили к провайдеру»
    велик: ответ выглядит настоящим. Но перехвативший обмен подсунет свой токен
    с чужой почтой — и войдёт кем угодно. Здесь провайдер отдаёт СВОИ ключи, а
    токен подписан другим: подпись не сойтись обязана.

    Эта проверка появилась не сразу: первая мутация «не проверять подпись» НЕ
    покраснела — значит, до неё подпись не доказывал ни один тест.
    """

    _, jwks = idp_key
    alien = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    alien_pem = alien.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()

    headers = await make_auth_headers(RoleEnum.ADMIN)
    me = await async_client.get("/api/v1/auth/me", headers=headers)
    email = me.json()["email"]
    await async_client.put(
        SETTINGS,
        json=_config_payload(email_domains=[email.rsplit("@", 1)[1]]),
        headers=headers,
    )
    start = await async_client.get(f"{SSO}/test/start")
    url = start.json()["authorization_url"]
    state = url.split("state=")[1].split("&")[0]
    nonce = url.split("nonce=")[1].split("&")[0]

    from app.api.routes import sso as sso_routes

    def factory(body: dict) -> str:
        return _id_token(alien_pem, audience="ptd-client", nonce=nonce, email=email, verified=True)

    monkeypatch.setattr(
        sso_routes,
        "_http_client",
        lambda: httpx.AsyncClient(transport=_transport(alien_pem, jwks, id_token_factory=factory)),
    )

    response = await async_client.get(f"{SSO}/callback", params={"code": "abc", "state": state})

    assert response.status_code == 401, response.text
