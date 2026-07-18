from __future__ import annotations

from app.services.document_quality import build_quality_report


def test_quality_report_blocks_release_on_missing_required_field() -> None:
    report = build_quality_report(
        data={"company_name": "Acme"},
        required_fields=["company_name", "order_date"],
    )
    assert report.release_blocked is True
    assert report.status == "failed"
    assert report.summary["critical"] == 1


def test_quality_report_allows_release_with_only_warnings() -> None:
    report = build_quality_report(
        data={"amount": "N/A"},
        required_fields=[],
        numeric_fields=["amount"],
    )
    assert report.release_blocked is False
    assert report.status == "passed"
    assert report.summary["warning"] == 1
