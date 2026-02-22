from __future__ import annotations

import csv
from io import StringIO


def parse_replace_csv(payload: bytes, *, limit: int = 5000) -> list[dict[str, object]]:
    text = payload.decode("utf-8-sig")
    result: list[dict[str, object]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(";", 1)
        if len(parts) != 2:
            continue
        source, target = parts
        result.append({"from": source, "to": target, "flags": {}, "priority": len(result)})
        if len(result) > limit:
            raise ValueError("replace map contains too many rules")
    return result
