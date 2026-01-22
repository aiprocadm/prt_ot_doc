from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class ComplianceChecker:
    jurisdiction: str

    def validate(self, context: dict[str, Any]) -> None:
        required = {"ru": ["inn", "ogrn"], "us": ["ein"]}
        missing = [key for key in required.get(self.jurisdiction, []) if key not in context]
        if missing:
            raise ValueError(f"Missing required fields: {', '.join(missing)}")
