from __future__ import annotations

import csv
from io import StringIO


def parse_replace_csv(payload: bytes, *, limit: int = 5000) -> list[dict[str, object]]:
    text = payload.decode("utf-8-sig")
    result: list[dict[str, object]] = []

    reader = csv.reader(StringIO(text), delimiter=";", quotechar='"')
    for row in reader:
        if not row:
            continue
        if row[0].lstrip().startswith("#"):
            continue
        if len(row) < 2:
            continue

        source = row[0].strip()
        target = row[1].strip()
        if not source:
            continue

        result.append({"from": source, "to": target, "flags": {}, "priority": len(result)})
        if len(result) > limit:
            raise ValueError("replace map contains too many rules")
    return result
