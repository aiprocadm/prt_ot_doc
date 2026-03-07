from __future__ import annotations

from datetime import datetime, timezone

from app.modules.ppe.services import (
    NormItem,
    PPEIssueEvent,
    PPENormService,
    PPEPersonalCardService,
    RiskPPEProjectionService,
)
from app.modules.risk.services import RiskCalculationService, RiskMethodologyService


def test_matrix_methodology_calculation() -> None:
    methodology = {
        "type": "matrix",
        "scale_json": {
            "level_rules": [
                {"min": 1, "max": 4, "level": "low"},
                {"min": 5, "max": 9, "level": "medium"},
                {"min": 10, "max": 15, "level": "high"},
                {"min": 16, "max": 25, "level": "critical"},
            ]
        },
    }
    result = RiskCalculationService.calculate_item(methodology, probability=4, severity=3)
    assert result.raw_score == 12
    assert result.risk_level == "high"


def test_fine_kinney_calculation() -> None:
    methodology = {
        "type": "fine_kinney",
        "formula_json": {
            "ranges": [
                {"min": 0, "max": 20, "level": "low"},
                {"min": 21, "max": 70, "level": "medium"},
                {"min": 71, "max": 200, "level": "high"},
                {"min": 201, "max": 999999, "level": "critical"},
            ]
        },
    }
    result = RiskCalculationService.calculate_item(methodology, probability=2, severity=6, exposure=10)
    assert result.raw_score == 120
    assert result.risk_level == "high"


def test_methodology_activation_rules() -> None:
    assert RiskMethodologyService.can_activate("draft", None, None) is True
    assert RiskMethodologyService.can_activate("archived", None, None) is False
    assert RiskMethodologyService.can_activate("active", "2026-12-31", "2026-01-01") is False


def test_ppe_required_union_and_missing_projection() -> None:
    required = PPENormService.required_union(
        position_id="pos-1",
        workplace_id="wp-1",
        hazard_ids={"haz-1"},
        norm_items=[
            NormItem("position", "pos-1", "helmet", 1),
            NormItem("workplace", "wp-1", "goggles", 1),
            NormItem("hazard", "haz-1", "respirator", 2),
            NormItem("hazard", "haz-2", "boots", 1),
        ],
    )
    assert required == {"helmet": 1, "goggles": 1, "respirator": 2}

    issued = {
        "helmet": {"current_quantity": 1.0, "next_due_at": None},
        "respirator": {"current_quantity": 1.0, "next_due_at": None},
    }
    assert RiskPPEProjectionService.missing_required(required, issued) == {"goggles": 1.0, "respirator": 1.0}


def test_issue_return_updates_personal_card_projection() -> None:
    now = datetime.now(tz=timezone.utc)
    events = [
        PPEIssueEvent("helmet", "issue", 2, now, wear_term_months=12),
        PPEIssueEvent("helmet", "return", 1, now),
        PPEIssueEvent("helmet", "replacement", 1, now),
    ]
    state = PPEPersonalCardService.apply_issue_events(events)
    assert state["helmet"]["current_quantity"] == 2.0
    assert state["helmet"]["next_due_at"] is not None
