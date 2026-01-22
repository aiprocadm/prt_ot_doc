from __future__ import annotations

from typing import Callable

from starlette import status
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.config import Settings, get_settings

try:  # pragma: no cover - exercised in integration tests
    from slowapi import Limiter, _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded
    from slowapi.middleware import SlowAPIMiddleware
    from slowapi.util import get_remote_address
except ImportError:  # pragma: no cover - fallback when slowapi is unavailable
    class RateLimitExceeded(Exception):
        """Fallback rate limit exception used when slowapi isn't installed."""

    class Limiter:
        def __init__(
            self,
            *,
            key_func: Callable[[Request], str] | None = None,
            default_limits: list[str] | None = None,
            headers_enabled: bool = False,
            storage_uri: str | None = None,
        ) -> None:
            self.key_func = key_func or (lambda request: "unknown")
            self.enabled = False

        def limit(
            self,
            _limit_value: str | Callable[[], str],
            *,
            key_func: Callable[[Request], str] | None = None,
        ) -> Callable[[Callable[..., object]], Callable[..., object]]:
            def decorator(func: Callable[..., object]) -> Callable[..., object]:
                return func

            return decorator

        def reset(self) -> None:
            """Compatibility hook mirroring slowapi's reset API."""

            return None

    async def _rate_limit_exceeded_handler(
        request: Request, exc: RateLimitExceeded
    ) -> JSONResponse:
        return JSONResponse(
            {"detail": "Rate limit exceeded"},
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        )

    def get_remote_address(request: Request) -> str:
        if request.client:
            return request.client.host
        return "unknown"

    class SlowAPIMiddleware:
        def __init__(self, app: ASGIApp, *, limiter: Limiter | None = None) -> None:
            self.app = app
            self.limiter = limiter

        async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
            await self.app(scope, receive, send)


_settings = get_settings()

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[],
    headers_enabled=True,
    storage_uri=_settings.rate_limit_storage_uri,
)
limiter.enabled = _settings.rate_limit_enabled

_rate_values = {
    "login_per_identity": _settings.rate_limit_login_per_identity,
    "upload_per_tenant": _settings.rate_limit_upload_per_tenant,
}


def configure_rate_limiter(settings: Settings | None = None) -> None:
    """Update limiter flags to reflect runtime configuration."""

    current = settings or get_settings()
    limiter.enabled = current.rate_limit_enabled
    _rate_values.update(
        {
            "login_per_identity": current.rate_limit_login_per_identity,
            "upload_per_tenant": current.rate_limit_upload_per_tenant,
        }
    )


def ip_subject_key(request: Request) -> str:
    """Return a limiter key combining caller IP and authenticated subject."""

    subject = getattr(request.state, "rate_limit_subject", None)
    if subject:
        identifier = str(subject)
    else:
        identifier = "anonymous"
    return f"{get_remote_address(request)}:{identifier}"


def ip_tenant_key(request: Request) -> str:
    """Return a limiter key combining caller IP and tenant scope."""

    tenant = getattr(request.state, "rate_limit_tenant_id", None)
    if tenant:
        identifier = str(tenant)
    else:
        identifier = "unknown"
    return f"{get_remote_address(request)}:{identifier}"


def login_per_identity() -> str:
    return _rate_values["login_per_identity"]


def upload_per_tenant() -> str:
    return _rate_values["upload_per_tenant"]


__all__ = [
    "RateLimitExceeded",
    "SlowAPIMiddleware",
    "configure_rate_limiter",
    "ip_subject_key",
    "ip_tenant_key",
    "login_per_identity",
    "upload_per_tenant",
    "limiter",
    "_rate_limit_exceeded_handler",
]
