from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.modules.capa.service import CorrectiveActionService, FindingService, PrescriptionService
from app.modules.inspection_prep.service import GapAnalysisService, InspectionPrepPackageService
from app.modules.inspections.service import InspectionChecklistService, InspectionService


def test_inspection_checklist_snapshot_semantics() -> None:
    source = [{"id": "i1", "title": "Check extinguisher", "result": "pass"}]
    snapshot = InspectionChecklistService.snapshot_items(source)
    source[0]["title"] = "Mutated"
    assert snapshot[0]["title"] == "Check extinguisher"


def test_finding_creation_from_failed_items() -> None:
    findings = InspectionService.findings_from_failed_items(
        [
            {"title": "PPE missing", "result": "fail", "severity_if_failed": "high"},
            {"title": "Markings", "result": "pass"},
        ]
    )
    assert len(findings) == 1
    assert findings[0]["severity"] == "high"


def test_prescription_aggregate_status_rules() -> None:
    assert PrescriptionService.aggregate_status(["open", "open"]) == "active"
    assert PrescriptionService.aggregate_status(["in_progress", "open"]) == "partially_closed"
    assert PrescriptionService.aggregate_status(["verified", "closed"]) == "closed"


def test_corrective_action_overdue_logic() -> None:
    # Service uses UTC date; local date.today() can disagree near timezone boundaries.
    today_utc = datetime.now(tz=timezone.utc).date()
    overdue_date = today_utc - timedelta(days=1)
    assert CorrectiveActionService.is_overdue("open", overdue_date) is True
    assert (
        CorrectiveActionService.mark_overdue_if_needed(due_date=overdue_date, status="open")
        == "overdue"
    )
    assert CorrectiveActionService.is_overdue("verified", overdue_date) is False


def test_inspection_prep_gap_detection_logic() -> None:
    gaps = GapAnalysisService.detect_gaps(
        missing_documents=2, open_prescriptions=1, overdue_actions=0, high_risks=1
    )
    assert {gap.gap_type for gap in gaps} == {"missing_doc", "open_prescription", "open_risk"}


def test_finding_requests_risk_review_on_high_severity() -> None:
    # Срез-117: проверка триггера пересмотра риска осталась только по живому
    # `FindingService`; мёртвый `RiskReviewTriggerService` удалён вместе со
    # слоем жизненного цикла `IncidentCase`.
    assert FindingService.should_request_risk_review("high") is True


def test_inspection_prep_readiness_score() -> None:
    assert InspectionPrepPackageService.readiness_score(total=10, present=7, replaced=1) == 80
