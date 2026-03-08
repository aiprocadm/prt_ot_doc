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
