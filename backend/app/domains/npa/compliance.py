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
        required = {"ru": ["inn", "ogrn"], "us": ["ein"]}.get(self.jurisdiction, [])
        missing_required = [key for key in required if not context.get(key)]
        linked_templates = list(bindings.get("templates") or [])
        linked_risks = list(bindings.get("risks") or [])
        linked_checklists = list(bindings.get("checklists") or [])
        linked_tasks = list(bindings.get("tasks") or [])
        linked_total = len(linked_templates) + len(linked_risks) + len(linked_checklists) + len(linked_tasks)
        status = "ok" if linked_total and not missing_required else "partial" if linked_total or missing_required else "draft"
        return {
            "jurisdiction": self.jurisdiction,
            "missing_required": missing_required,
            "linked_templates": linked_templates,
            "linked_risks": linked_risks,
            "linked_checklists": linked_checklists,
            "linked_tasks": linked_tasks,
            "linked_total": linked_total,
            "status": status,
            "severity": "high" if missing_required else "medium" if linked_total == 0 else "low",
            "summary": {
                "required_fields_total": len(required),
                "required_fields_present": len(required) - len(missing_required),
                "related_objects_total": linked_total,
            },
        }
