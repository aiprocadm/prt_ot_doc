from __future__ import annotations


class InspectionChecklistService:
    @staticmethod
    def snapshot_items(items: list[dict[str, object]]) -> list[dict[str, object]]:
        return [dict(item) for item in items]


class InspectionService:
    @staticmethod
    def findings_from_failed_items(run_items: list[dict[str, object]]) -> list[dict[str, object]]:
        return [
            {
                "source_type": "inspection",
                "title": str(item.get("title") or "Checklist item failed"),
                "severity": str(item.get("severity_if_failed") or "medium"),
                "finding_type": "nonconformity",
            }
            for item in run_items
            if item.get("result") == "fail"
        ]

    @staticmethod
    def can_close(*, has_blocking_open_items: bool, policy_requires_resolution: bool = True) -> bool:
        if not policy_requires_resolution:
            return True
        return not has_blocking_open_items


class InspectionPlanService:
    @staticmethod
    def plan_item_status(*, completed: bool, canceled: bool, overdue: bool) -> str:
        if canceled:
            return "canceled"
        if completed:
            return "completed"
        if overdue:
            return "overdue"
        return "planned"
