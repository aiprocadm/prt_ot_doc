from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import date, datetime
from enum import Enum
from typing import Any

MASK_KEYS = ("passport", "phone", "email", "snils", "inn")
SECRET_KEYS = ("password", "token", "secret", "key", "signature")
_MASK_RE = re.compile("|".join(MASK_KEYS), re.IGNORECASE)
_SECRET_RE = re.compile("|".join(SECRET_KEYS), re.IGNORECASE)


def _normalize(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {
            str(key): _normalize(value[key])
            for key in sorted(value.keys(), key=lambda item: str(item))
        }
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    return value


def field_diff(
    before: Mapping[str, Any] | None,
    after: Mapping[str, Any] | None,
    *,
    exclude: set[str] | None = None,
) -> dict[str, Any]:
    before_data = _normalize(before or {})
    after_data = _normalize(after or {})
    skipped = {"updated_at", "created_at", "version", *(exclude or set())}
    changes: dict[str, dict[str, Any]] = {}
    collections: dict[str, dict[str, Any]] = {}
    for key in sorted(set(before_data.keys()) | set(after_data.keys())):
        if key in skipped:
            continue
        prev = before_data.get(key)
        nxt = after_data.get(key)
        if _SECRET_RE.search(key):
            continue
        if isinstance(prev, list) or isinstance(nxt, list):
            prev_list = prev if isinstance(prev, list) else []
            nxt_list = nxt if isinstance(nxt, list) else []
            if prev_list != nxt_list:
                collections[key] = {
                    "added": [item for item in nxt_list if item not in prev_list],
                    "removed": [item for item in prev_list if item not in nxt_list],
                    "updated": [],
                }
            continue
        if prev != nxt:
            if _MASK_RE.search(key):
                prev = "***" if prev is not None else None
                nxt = "***" if nxt is not None else None
            changes[key] = {"before": prev, "after": nxt}
    return {"fields": changes, "collections": collections}


def mask_pii(payload: Mapping[str, Any]) -> dict[str, Any]:
    def _walk(value: Any, key: str | None = None) -> Any:
        if isinstance(value, Mapping):
            result: dict[str, Any] = {}
            for k, v in value.items():
                key_name = str(k).lower()
                if _SECRET_RE.search(key_name):
                    continue
                result[str(k)] = _walk(v, key_name)
            return result
        if isinstance(value, list):
            return [_walk(item, key) for item in value]
        if key and _MASK_RE.search(key):
            return "***"
        return value

    return _walk(dict(payload))
