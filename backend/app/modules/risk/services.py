"""Risk domain services for methodology-aware scoring and map projections."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

_RISK_LEVEL_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}


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
            return RiskCalcResult(
                raw_score=score, risk_level=RiskCalculationService._pick_level(score, rules)
            )

        if method_type == "fine_kinney":
            if exposure is None:
                raise ValueError("exposure is required for fine_kinney")
            score = probability * severity * exposure
            formula_json = methodology.get("formula_json")
            ranges = []
            if isinstance(formula_json, dict):
                ranges = formula_json.get("ranges", [])
            rules = RiskCalculationService._normalize_rules(ranges)
            return RiskCalcResult(
                raw_score=score, risk_level=RiskCalculationService._pick_level(score, rules)
            )

        if method_type == "custom":
            formula_json = (
                methodology.get("formula_json")
                if isinstance(methodology.get("formula_json"), dict)
                else {}
            )
            strategy = str(formula_json.get("strategy", "weighted_sum"))
            coefficients = (
                formula_json.get("coefficients", {}) if isinstance(formula_json, dict) else {}
            )
            probability_weight = float(coefficients.get("probability", 1))
            severity_weight = float(coefficients.get("severity", 1))
            exposure_weight = float(coefficients.get("exposure", 1))
            normalized_exposure = exposure if exposure is not None else 1.0
            if strategy == "weighted_product":
                score = (
                    (probability * probability_weight)
                    * (severity * severity_weight)
                    * (normalized_exposure * exposure_weight)
                )
            else:
                score = (
                    (probability * probability_weight)
                    + (severity * severity_weight)
                    + (normalized_exposure * exposure_weight)
                )
            rules = RiskCalculationService._level_rules(methodology.get("scale_json"))
            return RiskCalcResult(
                raw_score=round(score, 2),
                risk_level=RiskCalculationService._pick_level(score, rules),
            )

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
            if (
                isinstance(min_v, (int, float))
                and isinstance(max_v, (int, float))
                and isinstance(level, str)
            ):
                rules.append({"min": float(min_v), "max": float(max_v), "level": level})
        return rules

    @staticmethod
    def _pick_level(score: float, rules: list[dict[str, float | str]]) -> str:
        for rule in rules:
            min_v = float(rule["min"])
            max_v = float(rule["max"])
            if min_v <= score <= max_v:
                return str(rule["level"])
        if not rules:
            return "critical"
        # Score falls outside every configured range: clamp to the nearest band
        # rather than defaulting to "critical" (a residual of 0, below the lowest
        # band, must not be labelled the most severe level).
        by_min = sorted(rules, key=lambda r: float(r["min"]))
        if score < float(by_min[0]["min"]):
            return str(by_min[0]["level"])
        return str(by_min[-1]["level"])


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


class HazardService:
    """Resolve hazard IDs by entity bindings for risk-map generation."""

    @staticmethod
    def resolve_hazard_ids(
        *,
        entity_type: str,
        position_id: str | None,
        workplace_id: str | None,
        site_id: str | None,
        bindings: list[dict[str, str]],
    ) -> list[str]:
        scope: set[str] = set()
        if entity_type == "person":
            if position_id:
                scope.add(f"position:{position_id}")
            if workplace_id:
                scope.add(f"workplace:{workplace_id}")
            if site_id:
                scope.add(f"site:{site_id}")
        elif entity_type == "workplace":
            if workplace_id:
                scope.add(f"workplace:{workplace_id}")
            if site_id:
                scope.add(f"site:{site_id}")
        elif entity_type == "site" and site_id:
            scope.add(f"site:{site_id}")

        hazard_ids: list[str] = []
        for binding in bindings:
            binding_type = binding.get("binding_type")
            binding_id = binding.get("binding_id")
            hazard_id = binding.get("hazard_id")
            if not (binding_type and binding_id and hazard_id):
                continue
            if f"{binding_type}:{binding_id}" not in scope:
                continue
            if hazard_id not in hazard_ids:
                hazard_ids.append(hazard_id)
        return hazard_ids


class RiskMeasureService:
    """Helpers for residual risk rollup based on measure effectiveness."""

    @staticmethod
    def residual_from_measures(raw_score: float, effectiveness_scores: list[float]) -> float:
        score = raw_score
        for effect in effectiveness_scores:
            score = RiskCalculationService.calculate_residual(score, effect) or score
        return round(score, 2)


class RiskMapService:
    """In-memory map item lifecycle helpers used by route and job handlers."""

    @staticmethod
    def merge_items(
        *,
        existing_items: list[dict[str, object]],
        source_hazard_ids: list[str],
        methodology: dict[str, object],
    ) -> list[dict[str, object]]:
        indexed = {
            str(item["hazard_id"]): dict(item) for item in existing_items if "hazard_id" in item
        }
        now = datetime.now(tz=timezone.utc)

        for hazard_id in source_hazard_ids:
            item = indexed.get(hazard_id, {"hazard_id": hazard_id, "status": "active"})
            probability = float(item.get("probability_value") or 0)
            severity = float(item.get("severity_value") or 0)
            exposure_value = item.get("exposure_value")
            exposure = float(exposure_value) if exposure_value is not None else None

            if (
                probability > 0
                and severity > 0
                and (methodology.get("type") != "fine_kinney" or exposure)
            ):
                calc = RiskCalculationService.calculate_item(
                    methodology,
                    probability=probability,
                    severity=severity,
                    exposure=exposure,
                )
                item["raw_score"] = calc.raw_score
                item["risk_level"] = calc.risk_level
            item["status"] = "active"
            item["updated_at"] = now
            indexed[hazard_id] = item

        source_set = set(source_hazard_ids)
        for hazard_id, item in indexed.items():
            if hazard_id not in source_set:
                item["status"] = "archived"
                item["updated_at"] = now

        return list(indexed.values())

    @staticmethod
    def top_risk_level(levels: list[str]) -> str | None:
        if not levels:
            return None
        return sorted(levels, key=lambda lvl: _RISK_LEVEL_ORDER.get(lvl, -1), reverse=True)[0]
