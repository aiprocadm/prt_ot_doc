"""SEC-64 (разд. 64.1, строка CSRF): проверка Origin для cookie-аутентификации.

ТЗ: «CSRF: Anti-CSRF токены для cookie-сессий; SameSite; **проверка Origin для
мутаций**».

Сверка показала, что вердикт «CSRF неприменим, у нас Bearer» был бы неверным: у
``POST /auth/refresh`` refresh-токен берётся из **cookie** (`_extract_refresh_token`
предпочитает cookie телу запроса). Это единственная в API мутация, которую браузер
может выполнить, не имея доступа к токену, — то есть классическая мишень CSRF.

Что уже защищало и чего не хватало:

* ``SameSite=Strict`` + ``HttpOnly`` + ``Secure`` + путь-скоуп — cookie не уходит
  при кросс-сайтовом запросе в современных браузерах. Это основной рубеж;
* **проверки Origin не было**. SameSite — атрибут, который выставляет сервер, а
  соблюдает клиент: старый браузер, нестандартный клиент или будущее ослабление
  атрибута снимают защиту целиком. Origin проверяет сервер, и это независимый
  второй рубеж, которого ТЗ и требует.

Проверка намеренно узкая — **только когда запрос аутентифицирован cookie**.
Требовать Origin от всех мутаций нельзя: серверные API-клиенты его не шлют, и
такой гард сломал бы интеграции, ничего не добавив (Bearer-запрос подделать
кросс-сайтом невозможно — заголовок не проставится сам).
"""

from __future__ import annotations

from urllib.parse import urlsplit

from fastapi import HTTPException, Request, status

from app.core.errors import api_problem_detail

__all__ = ["CsrfOriginError", "assert_trusted_origin", "is_origin_allowed"]


class CsrfOriginError(HTTPException):
    """Мутация с cookie-аутентификацией пришла с недоверенного источника."""

    def __init__(self, reason: str) -> None:
        super().__init__(
            status.HTTP_403_FORBIDDEN,
            detail=api_problem_detail(
                code="CSRF_ORIGIN_REJECTED",
                message=reason,
                error_type="security",
            ),
        )


def _normalize(value: str) -> str:
    """Свести к ``scheme://host[:port]`` — сравнивать надо источник, а не путь."""

    parts = urlsplit(value.strip())
    if not parts.scheme or not parts.netloc:
        return ""
    return f"{parts.scheme}://{parts.netloc}".lower()


def is_origin_allowed(candidate: str, allowed: list[str]) -> bool:
    if "*" in allowed:
        return True
    normalized = _normalize(candidate)
    if not normalized:
        return False
    return any(_normalize(item) == normalized for item in allowed if item)


def assert_trusted_origin(request: Request, *, settings=None) -> None:
    """Отвергнуть cookie-аутентифицированную мутацию с чужого источника.

    ``Origin`` современные браузеры шлют на ВСЕХ небезопасных методах, включая
    same-origin, поэтому его отсутствие у cookie-запроса — само по себе аномалия.
    ``Referer`` принимается как запасной вариант ради старых клиентов.
    """

    if settings is None:
        from app.core.config import get_settings

        settings = get_settings()

    allowed = [str(item) for item in (getattr(settings, "allowed_origins", None) or [])]
    if "*" in allowed:
        # Конфигурация с открытым CORS не даёт этой проверке смысла; ругаться
        # здесь бесполезно — это решение принимается в настройках CORS.
        return

    origin = request.headers.get("origin") or ""
    if origin:
        if not is_origin_allowed(origin, allowed):
            raise CsrfOriginError(
                f"Origin {origin!r} is not allowed for cookie-authenticated requests"
            )
        return

    referer = request.headers.get("referer") or ""
    if referer:
        if not is_origin_allowed(referer, allowed):
            raise CsrfOriginError("Referer is not an allowed origin")
        return

    raise CsrfOriginError(
        "Cookie-authenticated mutation requires an Origin header; "
        "send the refresh token in the request body instead"
    )
