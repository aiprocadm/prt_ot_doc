from __future__ import annotations

import pytest

from app.domains.npa.compliance import ComplianceChecker


def test_compliance_checker_validate_requires_jurisdiction_fields() -> None:
    checker = ComplianceChecker(jurisdiction="ru")
    with pytest.raises(ValueError):
        checker.validate({"inn": "123"})


def test_compliance_impact_analysis_reports_summary_and_severity() -> None:
    checker = ComplianceChecker(jurisdiction="ru")
    payload = checker.impact_analysis({
        "inn": "123",
        "ogrn": "456",
        "bindings": {"templates": ["tpl-1"], "risks": ["risk-1"], "checklists": [], "tasks": ["task-1"]},
    })
    assert payload["status"] == "ok"
    assert payload["severity"] == "low"
    assert payload["summary"]["related_objects_total"] == 3
