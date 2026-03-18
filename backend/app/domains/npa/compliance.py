from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class ComplianceChecker:
    jurisdiction: str

    def validate(self, context: dict[str, Any]) -> None:
        required = {"ru": ["inn", "ogrn"], "us": ["ein"]}
        missing = [key for key in required.get(self.jurisdiction, []) if not context.get(key)]
        if missing:
            raise ValueError(f"Missing required fields: {', '.join(missing)}")

    def impact_analysis(self, context: dict[str, Any]) -> dict[str, Any]:
        bindings = context.get("bindings") or {}
        return {
            "jurisdiction": self.jurisdiction,
            "missing_required": [key for key in ("inn", "ogrn") if self.jurisdiction == "ru" and not context.get(key)],
            "linked_templates": list(bindings.get("templates") or []),
            "linked_risks": list(bindings.get("risks") or []),
            "linked_checklists": list(bindings.get("checklists") or []),
            "linked_tasks": list(bindings.get("tasks") or []),
            "status": "ok" if bindings else "partial",
        }
