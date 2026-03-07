"""Risk domain services for methodology-aware scoring and map projections."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class RiskCalcResult:
    raw_score: float
    risk_level: str


class RiskCalculationService:
    """Compute risk score/level for matrix and Fine-Kinney methodologies."""

    @staticmethod
    def calculate_item(
        methodology: dict[str, object],
        probability: float,
        severity: float,
        exposure: float | None = None,
    ) -> RiskCalcResult:
        method_type = str(methodology.get("type", "matrix"))
        if method_type == "matrix":
            score = probability * severity
            rules = RiskCalculationService._level_rules(methodology.get("scale_json"))
            return RiskCalcResult(raw_score=score, risk_level=RiskCalculationService._pick_level(score, rules))

        if method_type == "fine_kinney":
            if exposure is None:
                raise ValueError("exposure is required for fine_kinney")
            score = probability * severity * exposure
            formula_json = methodology.get("formula_json")
            ranges = []
            if isinstance(formula_json, dict):
                ranges = formula_json.get("ranges", [])
            rules = RiskCalculationService._normalize_rules(ranges)
            return RiskCalcResult(raw_score=score, risk_level=RiskCalculationService._pick_level(score, rules))

        raise ValueError(f"Unsupported methodology type: {method_type}")

    @staticmethod
    def calculate_residual(raw_score: float, effectiveness_score: float | None) -> float | None:
        if effectiveness_score is None:
            return None
        reduction = max(0.0, min(1.0, effectiveness_score / 100.0))
        return round(raw_score * (1 - reduction), 2)

    @staticmethod
    def _level_rules(raw_scale: object) -> list[dict[str, float | str]]:
        if isinstance(raw_scale, dict):
            return RiskCalculationService._normalize_rules(raw_scale.get("level_rules", []))
        return []

    @staticmethod
    def _normalize_rules(raw_rules: object) -> list[dict[str, float | str]]:
        if not isinstance(raw_rules, list):
            return []
        rules: list[dict[str, float | str]] = []
        for rule in raw_rules:
            if not isinstance(rule, dict):
                continue
            min_v = rule.get("min")
            max_v = rule.get("max")
            level = rule.get("level")
            if isinstance(min_v, (int, float)) and isinstance(max_v, (int, float)) and isinstance(level, str):
                rules.append({"min": float(min_v), "max": float(max_v), "level": level})
        return rules

    @staticmethod
    def _pick_level(score: float, rules: list[dict[str, float | str]]) -> str:
        for rule in rules:
            min_v = float(rule["min"])
            max_v = float(rule["max"])
            if min_v <= score <= max_v:
                return str(rule["level"])
        return "critical"


class RiskMethodologyService:
    """In-memory helper for methodology activation rule checks."""

    @staticmethod
    def can_activate(status: str, effective_from: object, effective_to: object) -> bool:
        if status not in {"draft", "active", "archived"}:
            return False
        if status == "archived":
            return False
        if effective_from and effective_to and effective_from > effective_to:
            return False
        return True
