"""Common response helpers for API endpoints."""

from __future__ import annotations

from typing import Any

__all__ = ["list_response"]


def list_response(items: list[dict[str, Any]], meta: dict[str, Any]) -> dict[str, Any]:
    """Standard envelope for paginated list responses."""

    return {"ok": True, "data": items, "meta": meta}
