from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
from enum import Enum
from typing import Any

MASK_KEYS = ("passport", "phone", "email")


def _normalize(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): _normalize(value[key]) for key in sorted(value.keys(), key=lambda item: str(item))}
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    return value


def field_diff(before: Mapping[str, Any] | None, after: Mapping[str, Any] | None, *, exclude: set[str] | None = None) -> dict[str, Any]:
    before_data = _normalize(before or {})
    after_data = _normalize(after or {})
    skipped = {"updated_at", "created_at", "version", *(exclude or set())}
    changes: dict[str, dict[str, Any]] = {}
    for key in sorted(set(before_data.keys()) | set(after_data.keys())):
        if key in skipped:
            continue
        prev = before_data.get(key)
        nxt = after_data.get(key)
        if prev != nxt:
            changes[key] = {"before": prev, "after": nxt}
    return {"fields": changes}


def mask_pii(payload: Mapping[str, Any]) -> dict[str, Any]:
    def _walk(value: Any, key: str | None = None) -> Any:
        if isinstance(value, Mapping):
            return {str(k): _walk(v, str(k).lower()) for k, v in value.items()}
        if isinstance(value, list):
            return [_walk(item, key) for item in value]
        if key and any(marker in key for marker in MASK_KEYS):
            return "***"
        return value

    return _walk(dict(payload))
