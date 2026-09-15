"""Обмен с провайдером единого входа (BIZ-53 разд. 53.3, срез-204).

Здесь ТОЛЬКО разговор с внешним провайдером: собрать адрес входа, обменять код
на токены, проверить подпись токена личности. Решения «пускать ли» живут в
``app.domains.sso.rules`` и проверяются без сети.

## Три решения, которые важнее кода

**1. HTTP-клиент внедряется, а не создаётся внутри.** Иначе проверить шов можно
было бы только с живым провайдером, то есть никогда. Урок среза-187 записан
кровью: тесты шва не заменяют теста МЕСТА ПОДКЛЮЧЕНИЯ, но и место подключения
надо чем-то проверять.

**2. Токен личности проверяется ПОДПИСЬЮ, а не разбирается как строка.**
Соблазн «взять claims без проверки, мы же только что сходили к провайдеру»
велик и смертелен: ответ мог прийти от кого угодно, кто перехватил обмен.
Проверяются подпись по JWKS, издатель, адресат и срок.

**3. ``nonce`` обязателен и сверяется.** Он привязывает токен к ИМЕННО ЭТОМУ
входу: без него чужой, но настоящий токен того же провайдера пустил бы человека
в чужую организацию.

Новых зависимостей не добавлено: подпись проверяется тем же ``python-jose``, что
подписывает наши собственные токены, а HTTP идёт через ``httpx``, который уже в
проекте. SAML потребовал бы библиотеку разбора и подписи XML — отдельная
поверхность атаки ради формата, который те же провайдеры отдают и через OIDC.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx
from jose import jwt
from jose.exceptions import JWTError

from app.domains.sso.rules import SsoConfig

__all__ = ["OidcError", "OidcIdentity", "authorization_url", "exchange_code"]


class OidcError(RuntimeError):
    """Провайдер ответил не тем. Наружу уходит как «вход не удался»."""


@dataclass(frozen=True, slots=True)
class OidcIdentity:
    """То, что провайдер сказал о человеке. Больше ничего мы не выдумываем."""

    subject: str
    email: str | None
    email_verified: bool
    full_name: str | None


def authorization_url(config: SsoConfig, *, redirect_uri: str, state: str, nonce: str) -> str:
    """Адрес, на который уводим человека к его провайдеру."""

    query = urlencode(
        {
            "response_type": "code",
            "client_id": config.client_id,
            "redirect_uri": redirect_uri,
            # `openid` обязателен, `email` — то, по чему мы находим сотрудника.
            "scope": "openid email profile",
            "state": state,
            "nonce": nonce,
        }
    )
    separator = "&" if "?" in config.authorization_endpoint else "?"
    return f"{config.authorization_endpoint}{separator}{query}"


async def exchange_code(
    config: SsoConfig,
    *,
    code: str,
    redirect_uri: str,
    nonce: str,
    client_secret: str,
    client: httpx.AsyncClient,
) -> OidcIdentity:
    """Обменять код на токены и проверить токен личности.

    ``client`` внедряется намеренно — см. заголовок модуля.
    """

    try:
        token_response = await client.post(
            config.token_endpoint,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": config.client_id,
                "client_secret": client_secret,
            },
            headers={"Accept": "application/json"},
        )
    except httpx.HTTPError as exc:  # pragma: no cover - сетевые сбои
        raise OidcError("провайдер недоступен") from exc
    if token_response.status_code != 200:
        # Тело ответа НЕ пересказываем наружу: в нём бывает секрет клиента,
        # который мы только что туда отправили.
        raise OidcError("провайдер отклонил обмен кода")
    payload = token_response.json()
    id_token = payload.get("id_token")
    if not id_token:
        raise OidcError("провайдер не вернул токен личности")

    try:
        jwks_response = await client.get(config.jwks_uri)
        jwks = jwks_response.json()
    except (httpx.HTTPError, ValueError) as exc:  # pragma: no cover - сетевые сбои
        raise OidcError("не удалось получить ключи провайдера") from exc

    try:
        claims = jwt.decode(
            id_token,
            jwks,
            audience=config.client_id,
            issuer=config.issuer,
            options={"verify_at_hash": False},
        )
    except JWTError as exc:
        raise OidcError("подпись токена личности не сошлась") from exc

    if claims.get("nonce") != nonce:
        # Токен настоящий, но не от ЭТОГО входа: без этой проверки чужой
        # действительный токен того же провайдера пустил бы человека сюда.
        raise OidcError("токен личности выдан не для этого входа")

    subject = str(claims.get("sub") or "").strip()
    if not subject:
        raise OidcError("провайдер не назвал идентификатор пользователя")
    return OidcIdentity(
        subject=subject,
        email=_first_string(claims, "email"),
        # Отсутствие признака трактуем как «НЕ подтверждён»: считать иначе
        # значило бы подставить правдоподобное значение вместо измерения.
        email_verified=bool(claims.get("email_verified") is True),
        full_name=_first_string(claims, "name"),
    )


def _first_string(claims: dict[str, Any], key: str) -> str | None:
    value = claims.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None
