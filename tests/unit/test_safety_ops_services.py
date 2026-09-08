from datetime import date, timedelta

from app.modules.capa import CorrectiveActionService, PrescriptionService
from app.modules.inspection_prep import GapAnalysisService
from app.modules.inspections import InspectionChecklistService, InspectionService


def test_checklist_snapshot_semantics() -> None:
    source = [{"title": "A", "result": "pass"}]
    snap = InspectionChecklistService.snapshot_items(source)
    source[0]["title"] = "B"
    assert snap[0]["title"] == "A"


def test_findings_from_failed_items() -> None:
    findings = InspectionService.findings_from_failed_items(
        [
            {"title": "PPE", "result": "fail", "severity_if_failed": "high"},
            {"title": "Training", "result": "pass"},
        ]
    )
    assert len(findings) == 1
    assert findings[0]["severity"] == "high"


def test_prescription_aggregate_status_rules() -> None:
    assert PrescriptionService.aggregate_status(["closed", "verified"]) == "closed"
    assert PrescriptionService.aggregate_status(["open", "in_progress"]) == "partially_closed"


def test_corrective_action_overdue_logic() -> None:
    assert CorrectiveActionService.is_overdue(
        "open", date.today() - timedelta(days=1), date.today()
    )
    assert not CorrectiveActionService.is_overdue(
        "verified", date.today() - timedelta(days=1), date.today()
    )


def test_gap_detection_logic() -> None:
    gaps = GapAnalysisService.detect_gaps(
        missing_documents=1, overdue_actions=1, open_prescriptions=0
    )
    assert len(gaps) == 2
