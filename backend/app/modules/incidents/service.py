from __future__ import annotations

from datetime import datetime, timezone

INCIDENT_FLOW = ["draft", "registered", "investigating", "awaiting_actions", "closed", "archived"]


class IncidentCaseService:
    @staticmethod
    def validate_transition(current: str, target: str) -> bool:
        try:
            return INCIDENT_FLOW.index(target) >= INCIDENT_FLOW.index(current)
        except ValueError:
            return False

    @staticmethod
    def can_close(*, has_open_actions: bool, manual_override: bool) -> bool:
        return (not has_open_actions) or manual_override

    @staticmethod
    def next_status_on_register(current: str) -> str:
        if current != "draft":
            raise ValueError("only draft incidents can be registered")
        return "registered"

    @classmethod
    def close_status(cls, *, has_open_actions: bool, manual_override: bool) -> str:
        if not cls.can_close(has_open_actions=has_open_actions, manual_override=manual_override):
            raise ValueError("cannot close incident with open actions")
        return "closed"


class IncidentInvestigationService:
    @staticmethod
    def complete_payload(status: str) -> dict[str, str | datetime]:
        if status not in {"in_progress", "completed"}:
            raise ValueError("invalid investigation status")
        return {"status": "completed", "completed_at": datetime.now(timezone.utc)}


class RiskReviewTriggerService:
    @staticmethod
    def needs_trigger(linked_risk_review_required: bool, severity: str) -> bool:
        return linked_risk_review_required or severity in {"high", "critical"}
