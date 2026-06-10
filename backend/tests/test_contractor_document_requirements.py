from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from types import SimpleNamespace

from app.domains.shared import ContingentItemStatus
from app.domains.contractors.documents import requirement_status, best_document
from app.domains.contractors.lifecycle import (
    DocumentRequirement,
    ReadinessStatus,
    evaluate_employee,
)
from app.modules.contractors.models import ComplianceStatus

TODAY = date(2026, 6, 10)


@dataclass
class _Doc:
    valid_until: date | None
    id: str = "d"
    doc_type: str = "license"


def test_no_candidates_is_missing():
    assert requirement_status([], TODAY) == ContingentItemStatus.MISSING


def test_open_ended_candidate_is_ok():
    assert requirement_status([_Doc(None)], TODAY) == ContingentItemStatus.OK


def test_future_candidate_is_ok():
    assert requirement_status([_Doc(TODAY + timedelta(days=90))], TODAY) == ContingentItemStatus.OK


def test_within_window_is_due_soon():
    assert requirement_status([_Doc(TODAY + timedelta(days=10))], TODAY) == ContingentItemStatus.DUE_SOON


def test_past_is_overdue():
    assert requirement_status([_Doc(TODAY - timedelta(days=1))], TODAY) == ContingentItemStatus.OVERDUE


def test_best_of_multiple_valid_beats_expired():
    docs = [_Doc(TODAY - timedelta(days=5), id="old"), _Doc(TODAY + timedelta(days=90), id="new")]
    assert requirement_status(docs, TODAY) == ContingentItemStatus.OK
    assert best_document(docs, TODAY).id == "new"


def test_best_document_none_when_empty():
    assert best_document([], TODAY) is None


# ---------------------------------------------------------------------------
# Document dimension in evaluate_employee
# ---------------------------------------------------------------------------


def _ready_emp():
    """An employee that is ALLOWED on the 3 base dimensions (so document rules decide)."""
    return SimpleNamespace(
        id="e1",
        contractor_id="c1",
        access_status=ComplianceStatus.VALID,
        training_status=ComplianceStatus.VALID,
        medical_status=ComplianceStatus.VALID,
        last_training_at=date(2026, 6, 1),       # within 365d window
        next_medical_at=date(2026, 12, 1),       # future
    )


def test_no_requirements_keeps_base_verdict_allowed():
    v = evaluate_employee(_ready_emp(), TODAY)
    assert v.status is ReadinessStatus.ALLOWED


def test_mandatory_missing_document_blocks():
    req = DocumentRequirement(doc_type="medical_cert", scope="employee", mandatory=True)
    v = evaluate_employee(_ready_emp(), TODAY, requirements=[req], employee_docs=[], company_docs=[])
    assert v.status is ReadinessStatus.BLOCKED
    assert "document:medical_cert" in v.violations


def test_mandatory_overdue_document_blocks():
    req = DocumentRequirement(doc_type="medical_cert", scope="employee", mandatory=True)
    doc = _Doc(TODAY - timedelta(days=1), doc_type="medical_cert")
    v = evaluate_employee(_ready_emp(), TODAY, requirements=[req], employee_docs=[doc])
    assert v.status is ReadinessStatus.BLOCKED
    assert "document:medical_cert" in v.violations


def test_non_mandatory_missing_document_warns():
    req = DocumentRequirement(doc_type="insurance", scope="company", mandatory=False)
    v = evaluate_employee(_ready_emp(), TODAY, requirements=[req])
    assert v.status is ReadinessStatus.WARNING
    assert "document:insurance" in v.warnings


def test_due_soon_document_warns_even_if_mandatory():
    req = DocumentRequirement(doc_type="medical_cert", scope="employee", mandatory=True)
    doc = _Doc(TODAY + timedelta(days=10), doc_type="medical_cert")
    v = evaluate_employee(_ready_emp(), TODAY, requirements=[req], employee_docs=[doc])
    assert v.status is ReadinessStatus.WARNING
    assert "document:medical_cert" in v.warnings


def test_scope_routing_company_doc_does_not_satisfy_employee_rule():
    req = DocumentRequirement(doc_type="sro", scope="employee", mandatory=True)
    company_doc = _Doc(TODAY + timedelta(days=90), doc_type="sro")
    # Document is in the company pool, but the rule looks at the employee pool → MISSING → BLOCKED.
    v = evaluate_employee(_ready_emp(), TODAY, requirements=[req], company_docs=[company_doc])
    assert v.status is ReadinessStatus.BLOCKED


def test_satisfied_company_rule_is_allowed():
    req = DocumentRequirement(doc_type="sro", scope="company", mandatory=True)
    company_doc = _Doc(TODAY + timedelta(days=90), doc_type="sro")
    v = evaluate_employee(_ready_emp(), TODAY, requirements=[req], company_docs=[company_doc])
    assert v.status is ReadinessStatus.ALLOWED
