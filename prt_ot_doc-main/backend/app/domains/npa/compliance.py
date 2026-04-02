from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

_REQUIRED_FIELDS = {"ru": ["inn", "ogrn"], "us": ["ein"]}


@dataclass(slots=True)
class ComplianceChecker:
    jurisdiction: str

    def validate(self, context: dict[str, Any]) -> None:
        required = _REQUIRED_FIELDS.get(self.jurisdiction, [])
        missing = [key for key in required if not context.get(key)]
        if missing:
            raise ValueError(f"Missing required fields: {', '.join(missing)}")

    def impact_analysis(self, context: dict[str, Any]) -> dict[str, Any]:
        bindings = context.get("bindings") or {}
        required = _REQUIRED_FIELDS.get(self.jurisdiction, [])
        missing_required = [key for key in required if not context.get(key)]
        linked_templates = list(bindings.get("templates") or [])
        linked_risks = list(bindings.get("risks") or [])
        linked_checklists = list(bindings.get("checklists") or [])
        linked_tasks = list(bindings.get("tasks") or [])
        linked_total = len(linked_templates) + len(linked_risks) + len(linked_checklists) + len(linked_tasks)

        effective_from = context.get("effective_from")
        effective_to = context.get("effective_to")
        today = date.today()
        effective_status = "draft"
        if effective_from:
            start = date.fromisoformat(str(effective_from))
            if effective_to:
                finish = date.fromisoformat(str(effective_to))
                effective_status = "expired" if finish < today else ("scheduled" if start > today else "active")
            else:
                effective_status = "scheduled" if start > today else "active"

        impacted_entities = sorted({*linked_templates, *linked_risks, *linked_checklists, *linked_tasks})
        status = "ok" if linked_total and not missing_required and effective_status in {"active", "draft"} else "partial" if linked_total or missing_required else "draft"
        if effective_status == "expired":
            status = "stale"

        tasks_to_create: list[str] = []
        if missing_required:
            tasks_to_create.append("fill_required_fields")
        if not linked_templates:
            tasks_to_create.append("bind_templates")
        if not linked_checklists:
            tasks_to_create.append("bind_checklists")

        severity = "high" if missing_required or effective_status == "expired" else "medium" if linked_total == 0 else "low"
        return {
            "jurisdiction": self.jurisdiction,
            "missing_required": missing_required,
            "linked_templates": linked_templates,
            "linked_risks": linked_risks,
            "linked_checklists": linked_checklists,
            "linked_tasks": linked_tasks,
            "linked_total": linked_total,
            "status": status,
            "severity": severity,
            "effective_status": effective_status,
            "impacted_entities": impacted_entities,
            "tasks_to_create": tasks_to_create,
            "summary": {
                "required_fields_total": len(required),
                "required_fields_present": len(required) - len(missing_required),
                "related_objects_total": linked_total,
                "impacted_entities_total": len(impacted_entities),
            },
        }
