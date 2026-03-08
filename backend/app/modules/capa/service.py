from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone


class FindingService:
    @staticmethod
    def should_request_risk_review(severity: str, linked_risk_map_id: str | None = None) -> bool:
        return severity in {"high", "critical"} or linked_risk_map_id is not None


class PrescriptionService:
    _CLOSED = {"closed", "verified"}

    @classmethod
    def aggregate_status(cls, item_statuses: list[str], *, current_status: str = "active") -> str:
        if not item_statuses:
            return current_status
        if all(status in cls._CLOSED for status in item_statuses):
            return "closed"
        if any(status in {"in_progress", "resolved", "verified", "closed"} for status in item_statuses):
            return "partially_closed"
        return "active"


@dataclass(frozen=True)
class VerificationResult:
    status: str
    effectiveness_status: str
    verification_comment: str | None


class CorrectiveActionService:
    @staticmethod
    def is_overdue(status: str, due_date: date | None, now: date | None = None) -> bool:
        if due_date is None or status in {"done", "verified", "canceled"}:
            return False
        check_date = now or datetime.now(tz=timezone.utc).date()
        return due_date < check_date

    @classmethod
    def mark_overdue_if_needed(cls, *, due_date: date | None, status: str) -> str:
        return "overdue" if cls.is_overdue(status, due_date) else status

    @staticmethod
    def apply_verification(*, is_effective: bool, partially_effective: bool = False, comment: str | None = None) -> VerificationResult:
        if is_effective:
            return VerificationResult(status="verified", effectiveness_status="effective", verification_comment=comment)
        if partially_effective:
            return VerificationResult(status="verified", effectiveness_status="partial", verification_comment=comment)
        return VerificationResult(status="verified", effectiveness_status="ineffective", verification_comment=comment)
