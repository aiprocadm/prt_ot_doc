"""Per-request context helpers for logging and audit."""

from __future__ import annotations

from contextvars import ContextVar, Token
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - type-checker only
    from starlette.requests import Request

_USER_ID_VAR: ContextVar[str | None] = ContextVar("current_user_id", default=None)
_SCOPE_VAR: ContextVar[dict[str, Any] | None] = ContextVar("request_scope", default=None)


def get_current_user_id() -> str | None:
    return _USER_ID_VAR.get()


def set_current_user_id(value: str | None) -> Token[str | None]:
    return _USER_ID_VAR.set(value)


def reset_current_user_id(token: Token[str | None]) -> None:
    _USER_ID_VAR.reset(token)


def set_request_scope(scope: dict[str, Any] | None) -> Token[dict[str, Any] | None]:
    return _SCOPE_VAR.set(scope)


def reset_request_scope(token: Token[dict[str, Any] | None]) -> None:
    _SCOPE_VAR.reset(token)


def get_current_request() -> Request | None:
    """Rebuild a ``Request`` for the in-flight ASGI scope, or ``None`` off-request.

    ``@audit_operation`` needs the request to attribute an event (actor, IP,
    trace), but a handler only receives one if it happens to declare a
    ``request`` parameter -- and most do not, which silently disabled auditing
    on them. Reading the scope from context instead makes the decorator
    independent of the handler signature.

    A fresh ``Request`` is safe here: ``request.state`` is backed by
    ``scope["state"]``, so attributes set by auth on the handler's own
    ``Request`` (notably ``current_user_id``) are visible through this one.
    The body is never touched, so no receive-channel interference.
    """

    scope = _SCOPE_VAR.get()
    if scope is None or scope.get("type") != "http":
        return None
    from starlette.requests import Request  # noqa: PLC0415 - avoid import cycle at module load

    return Request(scope)


__all__ = [
    "get_current_user_id",
    "set_current_user_id",
    "reset_current_user_id",
    "set_request_scope",
    "reset_request_scope",
    "get_current_request",
]
