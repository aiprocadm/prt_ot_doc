"""SEC-68: anti-abuse внешнего контура (клиентский портал, разд. 68.1–68.2).

Внешние пользователи — за периметром, их устройства не контролируются, а вход в
портал — это один токен в ссылке. Разд. 68.1 требует защиты от перебора, разд. 68.2 —
«отдельный rate limit и anti-abuse для внешних эндпоинтов, **жёстче, чем для
внутренних**». До этого модуля у портальных ручек не было ни того, ни другого:
подобрать 192-битный токен нереально, но неограниченная скорость попыток снимает
единственную стоимость атаки и оставляет открытым тривиальный DoS.

Два независимых счётчика, оба по IP:

* **общий поток** (``PORTAL_RATE_LIMIT_PER_IP``) — сколько портальных запросов в
  минуту допустимо вообще;
* **неудачные аутентификации** (``PORTAL_AUTH_FAILURES_PER_IP``) — отдельный, гораздо
  более строгий счётчик. Он ловит именно перебор: успешные запросы его не тратят,
  поэтому легитимный клиент никогда его не касается.

Хранилище берётся у уже настроенного лимитера приложения
(``RATE_LIMIT_STORAGE_URI``), поэтому при сконфигурированном Redis счётчики общие
для всех воркеров. На ``memory://`` они процесс-локальны — это ослабляет защиту при
нескольких воркерах, но не отключает её; для внешнего контура в проде Redis нужен, и
об этом сказано в docs/security/EXTERNAL_PERIMETER.md.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from fastapi import HTTPException, Request, status
from limits import RateLimitItem, parse
from limits.storage import MemoryStorage, storage_from_string
from limits.strategies import FixedWindowRateLimiter

from app.core.errors import api_problem_detail

logger = logging.getLogger(__name__)

_TRAFFIC_PREFIX = "portal:traffic"
_FAILURE_PREFIX = "portal:auth-fail"
_SIGNUP_PREFIX = "public:signup"


@dataclass
class _Guard:
    storage_uri: str
    traffic: RateLimitItem
    failures: RateLimitItem
    #: BIZ-53 срез-3: свой счётчик для самостоятельной регистрации. Создание
    #: арендатора несопоставимо дороже обычного запроса, поэтому общий
    #: портальный лимит для него слишком мягкий.
    signup: RateLimitItem
    limiter: FixedWindowRateLimiter


_guard: _Guard | None = None


def _build_guard(settings) -> _Guard:
    uri = getattr(settings, "rate_limit_storage_uri", "memory://") or "memory://"
    try:
        storage = storage_from_string(uri)
    except Exception:  # pragma: no cover - защита не должна ронять приложение
        logger.warning("portal.anti_abuse.storage_fallback", extra={"uri": uri})
        storage = MemoryStorage()
    return _Guard(
        storage_uri=uri,
        traffic=parse(getattr(settings, "portal_rate_limit_per_ip", "60/minute")),
        failures=parse(getattr(settings, "portal_auth_failures_per_ip", "10/hour")),
        signup=parse(getattr(settings, "self_service_signup_per_ip", "3/hour")),
        limiter=FixedWindowRateLimiter(storage),
    )


def _get_guard(settings=None) -> _Guard:
    global _guard
    from app.core.config import get_settings

    current = settings or get_settings()
    uri = getattr(current, "rate_limit_storage_uri", "memory://") or "memory://"
    if _guard is None or _guard.storage_uri != uri:
        _guard = _build_guard(current)
    return _guard


def reset_guard() -> None:
    """Сбросить кеш guard'а (нужен тестам и при перезагрузке настроек)."""

    global _guard
    _guard = None


def _client_ip(request: Request | None) -> str:
    if request is None or request.client is None:
        return "unknown"
    return request.client.host or "unknown"


def _enabled(settings) -> bool:
    return bool(getattr(settings, "rate_limit_enabled", True))


def _too_many(code: str, message: str) -> HTTPException:
    return HTTPException(
        status.HTTP_429_TOO_MANY_REQUESTS,
        detail=api_problem_detail(code=code, message=message, error_type="rate_limit"),
    )


def enforce_portal_traffic(request: Request | None, *, settings=None) -> None:
    """Общий лимит портальных запросов по IP. Вызывается на каждом обращении."""

    from app.core.config import get_settings

    current = settings or get_settings()
    if not _enabled(current):
        return
    guard = _get_guard(current)
    ip = _client_ip(request)
    if not guard.limiter.hit(guard.traffic, _TRAFFIC_PREFIX, ip):
        logger.warning("portal.anti_abuse.rate_limited", extra={"ip": ip})
        raise _too_many(
            "PORTAL_RATE_LIMITED", "Too many requests to the client portal from this address"
        )


def enforce_signup_attempts(request: Request | None, *, settings=None) -> None:
    """Лимит попыток самостоятельной регистрации по IP (BIZ-53 срез-3).

    Отдельный и строгий: каждая успешная регистрация создаёт СХЕМУ в базе.
    Считается ДО создания, поэтому перебор не стоит нам развёрнутых арендаторов.

    Работает независимо от общего выключателя внешнего контура: регистрация
    может быть открыта и там, где клиентский портал не используется.
    """

    from app.core.config import get_settings

    current = settings or get_settings()
    guard = _get_guard(current)
    ip = _client_ip(request)
    if not guard.limiter.hit(guard.signup, _SIGNUP_PREFIX, ip):
        logger.warning("signup.anti_abuse.rate_limited", extra={"ip": ip})
        raise _too_many("SIGNUP_RATE_LIMITED", "Too many registration attempts from this address")


def assert_not_locked_out(request: Request | None, *, settings=None) -> None:
    """Отказать, если с этого IP уже исчерпан лимит НЕУДАЧНЫХ попыток.

    Проверяется до обращения к базе: смысл в том, чтобы перебор не стоил нам
    запроса в БД на каждую попытку.
    """

    from app.core.config import get_settings

    current = settings or get_settings()
    if not _enabled(current):
        return
    guard = _get_guard(current)
    ip = _client_ip(request)
    if not guard.limiter.test(guard.failures, _FAILURE_PREFIX, ip):
        logger.warning("portal.anti_abuse.locked_out", extra={"ip": ip})
        raise _too_many(
            "PORTAL_TOKEN_LOCKED_OUT",
            "Too many invalid portal tokens from this address; try again later",
        )


def record_auth_failure(request: Request | None, *, settings=None) -> None:
    """Учесть неудачную аутентификацию по токену.

    Тратится ТОЛЬКО на неудачах — легитимный клиент этот счётчик не касается, поэтому
    порог можно держать низким, не мешая нормальной работе.
    """

    from app.core.config import get_settings

    current = settings or get_settings()
    if not _enabled(current):
        return
    guard = _get_guard(current)
    guard.limiter.hit(guard.failures, _FAILURE_PREFIX, _client_ip(request))


__all__ = [
    "assert_not_locked_out",
    "enforce_portal_traffic",
    "record_auth_failure",
    "reset_guard",
]
