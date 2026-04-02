"""Request-scoped tracing utilities for API handlers."""

from __future__ import annotations

import uuid
from typing import Final

from fastapi import Request

from app.core.config import get_settings

TRACE_HEADER: Final[str] = get_settings().trace_header_name
TRACE_HEADER_ALIASES: Final[tuple[str, ...]] = (
    "X-Trace-Id",
    "X-Correlation-Id",
    "X-Request-Id",
)


def _normalize_trace_id(value: str | None) -> str | None:
    if not value:
        return None
    candidate = value.strip()
    if not candidate:
        return None
    return candidate[:128]


def _read_trace_from_headers(request: Request, header_name: str | None) -> str | None:
    names: list[str] = []
    if header_name:
        names.append(header_name)
    names.extend(alias for alias in TRACE_HEADER_ALIASES if alias not in names)
    for name in names:
        resolved = _normalize_trace_id(request.headers.get(name))
        if resolved:
            return resolved
    return None


def get_trace_id(request: Request, header_name: str | None = None) -> str:
    """Return a trace identifier for the current request.

    The identifier is retrieved from the request state when available, falls back to
    the incoming trace header, and ultimately generates a new UUID when none is
    supplied.
    """

    trace_id = _normalize_trace_id(getattr(request.state, "trace_id", None))
    if not trace_id:
        header_key = header_name or TRACE_HEADER
        trace_id = _read_trace_from_headers(request, header_key)

    if not trace_id:
        trace_id = uuid.uuid4().hex

    setattr(request.state, "trace_id", trace_id)
    return trace_id


__all__ = ["TRACE_HEADER", "get_trace_id"]
