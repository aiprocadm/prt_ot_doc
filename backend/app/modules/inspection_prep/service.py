from __future__ import annotations


class InspectionPrepPackageService:
    pass


class GapAnalysisService:
    @staticmethod
    def detect_gaps(*, missing_documents: int, overdue_actions: int, open_prescriptions: int) -> list[dict[str, str]]:
        gaps: list[dict[str, str]] = []
        if missing_documents:
            gaps.append({"gap_type": "missing_doc", "severity": "high", "title": "Missing documents"})
        if overdue_actions:
            gaps.append({"gap_type": "custom", "severity": "high", "title": "Overdue corrective actions"})
        if open_prescriptions:
            gaps.append({"gap_type": "open_prescription", "severity": "medium", "title": "Open prescriptions"})
        return gaps
