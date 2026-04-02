"""Utilities for correlating logs and responses via trace identifiers."""

from __future__ import annotations

import contextvars
from dataclasses import dataclass
from typing import Optional

_TRACE_ID: contextvars.ContextVar[str] = contextvars.ContextVar(
    "trace_id", default="unknown"
)


@dataclass(frozen=True, slots=True)
class TraceContext:
    """Active trace context details."""

    trace_id: str


def set_trace_id(value: str) -> contextvars.Token[str]:
    """Set the active trace identifier and return the context token."""

    normalized = value.strip() or "unknown"
    return _TRACE_ID.set(normalized)


def get_trace_id(default: Optional[str] = None) -> str:
    """Return the current trace identifier."""

    trace_id = _TRACE_ID.get()
    if trace_id == "unknown" and default is not None:
        return default
    return trace_id


def reset_trace_id(token: contextvars.Token[str]) -> None:
    """Restore the trace identifier to a previous state."""

    _TRACE_ID.reset(token)


__all__ = ["TraceContext", "get_trace_id", "reset_trace_id", "set_trace_id"]
