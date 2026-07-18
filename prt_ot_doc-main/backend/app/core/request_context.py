"""Per-request context helpers for logging."""

from __future__ import annotations

from contextvars import ContextVar, Token

_USER_ID_VAR: ContextVar[str | None] = ContextVar("current_user_id", default=None)


def get_current_user_id() -> str | None:
    return _USER_ID_VAR.get()


def set_current_user_id(value: str | None) -> Token[str | None]:
    return _USER_ID_VAR.set(value)


def reset_current_user_id(token: Token[str | None]) -> None:
    _USER_ID_VAR.reset(token)


__all__ = ["get_current_user_id", "set_current_user_id", "reset_current_user_id"]
