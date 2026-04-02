from __future__ import annotations

import hashlib
import json
from typing import Any


def make_request_hash(path: str, tenant_id: str, user_id: str, body: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps({"path": path, "tenant_id": tenant_id, "user_id": user_id, "body": body}, sort_keys=True).encode()
    ).hexdigest()


def cond_matches(conditions: dict[str, Any], ctx: dict[str, Any]) -> int:
    matched = 0
    for key, value in (conditions or {}).items():
        if value is None:
            continue
        if ctx.get(key) == value:
            matched += 1
        else:
            return -1
    return matched
