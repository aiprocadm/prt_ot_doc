"""Request-scoped tracing utilities for API handlers."""

from __future__ import annotations

import uuid
from typing import Final

from fastapi import Request

from app.core.config import get_settings

TRACE_HEADER: Final[str] = get_settings().trace_header_name


def get_trace_id(request: Request, header_name: str | None = None) -> str:
    """Return a trace identifier for the current request.

    The identifier is retrieved from the request state when available, falls back to
    the incoming trace header, and ultimately generates a new UUID when none is
    supplied.
    """

    trace_id = getattr(request.state, "trace_id", None)
    if trace_id:
        return trace_id

    header_key = header_name or TRACE_HEADER
    header_value: str | None = None
    if header_key:
        header_value = request.headers.get(header_key)

    if header_value:
        candidate = header_value.strip()
        if candidate:
            trace_id = candidate[:128]

    if not trace_id:
        trace_id = uuid.uuid4().hex

    setattr(request.state, "trace_id", trace_id)
    return trace_id


__all__ = ["TRACE_HEADER", "get_trace_id"]
