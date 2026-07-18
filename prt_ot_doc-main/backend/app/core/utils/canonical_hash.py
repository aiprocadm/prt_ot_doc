from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any


def _normalize(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _normalize(v) for k, v in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    if isinstance(value, tuple):
        return [_normalize(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def canonical_json_bytes(payload: dict[str, Any], *, mapping: dict[str, Any] | None = None, template_version_id: str | None = None, options: dict[str, Any] | None = None) -> bytes:
    canonical = {
        "payload": payload,
        "mapping": mapping or {},
        "template_version_id": template_version_id,
        "options": options or {},
    }
    normalized = _normalize(canonical)
    return json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def compute_sha256_input(payload: dict[str, Any], *, mapping: dict[str, Any] | None = None, template_version_id: str | None = None, options: dict[str, Any] | None = None) -> str:
    return hashlib.sha256(canonical_json_bytes(payload, mapping=mapping, template_version_id=template_version_id, options=options)).hexdigest()

