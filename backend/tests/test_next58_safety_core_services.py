from __future__ import annotations

from datetime import datetime, timezone

from app.modules.ppe.services import (
    NormItem,
    PPEIssueEvent,
    PPENormService,
    PPEPersonalCardService,
    PackSafetySummaryService,
    RiskPPEProjectionService,
)
from app.modules.risk.services import (
    HazardService,
    RiskCalculationService,
    RiskMapService,
    RiskMeasureService,
    RiskMethodologyService,
)


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


def test_hazard_binding_resolution_for_person() -> None:
    hazard_ids = HazardService.resolve_hazard_ids(
        entity_type="person",
        position_id="pos-1",
        workplace_id="wp-1",
        site_id="site-1",
        bindings=[
            {"binding_type": "position", "binding_id": "pos-1", "hazard_id": "h-pos"},
            {"binding_type": "workplace", "binding_id": "wp-1", "hazard_id": "h-wp"},
            {"binding_type": "site", "binding_id": "site-1", "hazard_id": "h-site"},
            {"binding_type": "site", "binding_id": "site-2", "hazard_id": "h-other"},
        ],
    )
    assert hazard_ids == ["h-pos", "h-wp", "h-site"]


def test_residual_risk_update() -> None:
    residual = RiskMeasureService.residual_from_measures(100, [10, 20])
    assert residual == 72


def test_risk_map_generation_archives_removed_bindings() -> None:
    methodology = {
        "type": "matrix",
        "scale_json": {"level_rules": [{"min": 1, "max": 25, "level": "low"}]},
    }
    merged = RiskMapService.merge_items(
        existing_items=[
            {"hazard_id": "h-1", "probability_value": 2, "severity_value": 2},
            {"hazard_id": "h-old", "probability_value": 3, "severity_value": 3},
        ],
        source_hazard_ids=["h-1", "h-2"],
        methodology=methodology,
    )
    by_id = {item["hazard_id"]: item for item in merged}
    assert by_id["h-1"]["status"] == "active"
    assert by_id["h-2"]["status"] == "active"
    assert by_id["h-old"]["status"] == "archived"


def test_pack_safety_clearance_rule() -> None:
    assert PackSafetySummaryService.has_clearance(risk_levels=["low"], missing_ppe={}) is True
    assert PackSafetySummaryService.has_clearance(risk_levels=["high"], missing_ppe={}) is False
    assert PackSafetySummaryService.has_clearance(risk_levels=["medium"], missing_ppe={"helmet": 1}) is False
