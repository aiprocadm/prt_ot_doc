from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PrepGap:
    gap_type: str
    severity: str
    title: str


class InspectionPrepPackageService:
    @staticmethod
    def readiness_score(*, total: int, present: int, replaced: int = 0) -> int:
        if total <= 0:
            return 0
        safe_present = max(0, present) + max(0, replaced)
        return max(0, min(100, int((safe_present / total) * 100)))

    @staticmethod
    def collect_required_items() -> list[dict[str, str]]:
        return [
            {"item_type": "risk_map", "title": "Risk map", "status": "required"},
            {"item_type": "ppe_card", "title": "PPE completeness", "status": "required"},
            {"item_type": "training_record", "title": "Training records", "status": "required"},
        ]


class GapAnalysisService:
    @staticmethod
    def detect_gaps(*, missing_documents: int, open_prescriptions: int, overdue_actions: int, high_risks: int) -> list[PrepGap]:
        gaps: list[PrepGap] = []
        if missing_documents > 0:
            gaps.append(PrepGap("missing_doc", "high", "Missing mandatory documents"))
        if open_prescriptions > 0:
            gaps.append(PrepGap("open_prescription", "high", "Open prescriptions detected"))
        if overdue_actions > 0:
            gaps.append(PrepGap("custom", "medium", "Overdue corrective actions"))
        if high_risks > 0:
            gaps.append(PrepGap("open_risk", "critical", "Open high or critical risks"))
        return gaps
