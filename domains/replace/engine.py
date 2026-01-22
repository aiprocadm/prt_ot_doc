from __future__ import annotations

from typing import Any


class ReplaceEngine:
    def apply(self, context: dict[str, Any], replacements: dict[str, str]) -> dict[str, Any]:
        updated = dict(context)
        for key, value in replacements.items():
            if key in updated:
                updated[key] = value
        return updated
