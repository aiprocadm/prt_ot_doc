from __future__ import annotations

import re
from typing import Any

_PATTERN = re.compile(r"\{\{\s*([\w.]+)\s*\}\}")


def _resolve_path(data: dict[str, Any], key: str) -> tuple[str | None, bool]:
    node: Any = data
    for part in key.split("."):
        if not isinstance(node, dict) or part not in node:
            return None, False
        node = node[part]
    if node is None:
        return "", True
    return str(node), True


def render_placeholders(text: str | None, data: dict[str, Any], *, strict: bool = False) -> tuple[str, list[str]]:
    unresolved: list[str] = []
    value = text or ""

    def repl(match: re.Match[str]) -> str:
        key = match.group(1)
        resolved, found = _resolve_path(data, key)
        if not found:
            unresolved.append(key)
            return match.group(0) if strict else ""
        return resolved or ""

    return _PATTERN.sub(repl, value), unresolved
