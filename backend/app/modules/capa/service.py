from __future__ import annotations

from datetime import date


class FindingService:
    pass


class PrescriptionService:
    @staticmethod
    def aggregate_status(item_statuses: list[str]) -> str:
        if not item_statuses:
            return "draft"
        if all(s in {"closed", "verified"} for s in item_statuses):
            return "closed"
        if any(s in {"in_progress", "resolved", "verified"} for s in item_statuses):
            return "partially_closed"
        return "active"


class CorrectiveActionService:
    @staticmethod
    def is_overdue(status: str, due_date: date | None, today: date) -> bool:
        if due_date is None:
            return False
        return status not in {"done", "verified", "canceled"} and due_date < today
