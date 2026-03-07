"""PPE domain services for requirement unions and personal-card projections."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


@dataclass(slots=True)
class NormItem:
    applies_to_type: str
    applies_to_id: str
    ppe_catalog_id: str
    quantity: float
    period_months: int | None = None


@dataclass(slots=True)
class PPEIssueEvent:
    ppe_catalog_id: str
    issue_type: str
    quantity: float
    issued_at: datetime
    wear_term_months: int | None = None
    period_months: int | None = None


class PPENormService:
    @staticmethod
    def required_union(
        *,
        position_id: str | None,
        workplace_id: str | None,
        hazard_ids: set[str],
        norm_items: list[NormItem],
    ) -> dict[str, float]:
        totals: dict[str, float] = {}

        def include(item: NormItem) -> bool:
            if item.applies_to_type == "position" and position_id:
                return item.applies_to_id == position_id
            if item.applies_to_type == "workplace" and workplace_id:
                return item.applies_to_id == workplace_id
            if item.applies_to_type == "hazard":
                return item.applies_to_id in hazard_ids
            return False

        for item in norm_items:
            if not include(item):
                continue
            totals[item.ppe_catalog_id] = max(totals.get(item.ppe_catalog_id, 0.0), item.quantity)
        return totals




class PPEIssueService:
    @staticmethod
    def validate_issue_type(issue_type: str) -> str:
        allowed = {"issue", "return", "writeoff", "replacement"}
        normalized = issue_type.strip().lower()
        if normalized not in allowed:
            raise ValueError("unsupported issue_type")
        return normalized


class PPEPersonalCardService:
    @staticmethod
    def apply_issue_events(events: list[PPEIssueEvent]) -> dict[str, dict[str, datetime | float | None]]:
        state: dict[str, dict[str, datetime | float | None]] = {}

        for event in sorted(events, key=lambda item: item.issued_at):
            bucket = state.setdefault(event.ppe_catalog_id, {"current_quantity": 0.0, "next_due_at": None})
            if event.issue_type in {"issue", "replacement"}:
                bucket["current_quantity"] = float(bucket["current_quantity"]) + event.quantity
            elif event.issue_type in {"return", "writeoff"}:
                bucket["current_quantity"] = max(0.0, float(bucket["current_quantity"]) - event.quantity)

            months = event.period_months or event.wear_term_months
            if months:
                bucket["next_due_at"] = event.issued_at + timedelta(days=months * 30)

        return state


class RiskPPEProjectionService:
    @staticmethod
    def missing_required(required: dict[str, float], issued_state: dict[str, dict[str, datetime | float | None]]) -> dict[str, float]:
        missing: dict[str, float] = {}
        for catalog_id, qty in required.items():
            current = float(issued_state.get(catalog_id, {}).get("current_quantity", 0.0))
            if current < qty:
                missing[catalog_id] = round(qty - current, 2)
        return missing

    @staticmethod
    def expiring_soon(issued_state: dict[str, dict[str, datetime | float | None]], days: int = 30) -> list[str]:
        now = datetime.now(tz=timezone.utc)
        threshold = now + timedelta(days=days)
        return [
            catalog_id
            for catalog_id, bucket in issued_state.items()
            if isinstance(bucket.get("next_due_at"), datetime) and now <= bucket["next_due_at"] <= threshold
        ]
