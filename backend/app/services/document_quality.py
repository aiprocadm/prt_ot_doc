from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from app.schemas.document_quality import QualityIssue, QualityReport

_PLACEHOLDER_RE = re.compile(r"\{\{\s*([a-zA-Z0-9_\.]+)\s*\}\}")


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) == 0
    return False


def _validate_required_fields(
    data: dict[str, Any], required_fields: list[str]
) -> list[QualityIssue]:
    issues: list[QualityIssue] = []
    for field_name in required_fields:
        if _is_empty(data.get(field_name)):
            issues.append(
                QualityIssue(
                    code="REQUIRED_FIELD_MISSING",
                    message=f"Required field '{field_name}' is missing",
                    severity="critical",
                    stage="quality_gate",
                    details={"field": field_name},
                )
            )
    return issues


def _validate_value_types(
    data: dict[str, Any], date_fields: list[str], numeric_fields: list[str]
) -> list[QualityIssue]:
    issues: list[QualityIssue] = []
    for field_name in date_fields:
        value = data.get(field_name)
        if _is_empty(value):
            continue
        if isinstance(value, (date, datetime)):
            continue
        if isinstance(value, str):
            try:
                datetime.fromisoformat(value)
                continue
            except ValueError:
                pass
        issues.append(
            QualityIssue(
                code="INVALID_DATE",
                message=f"Field '{field_name}' has invalid date value",
                severity="critical",
                stage="quality_gate",
                details={"field": field_name, "value": value},
            )
        )
    for field_name in numeric_fields:
        value = data.get(field_name)
        if _is_empty(value):
            continue
        try:
            Decimal(str(value))
        except (InvalidOperation, ValueError):
            issues.append(
                QualityIssue(
                    code="INVALID_NUMBER",
                    message=f"Field '{field_name}' has invalid numeric value",
                    severity="warning",
                    stage="quality_gate",
                    details={"field": field_name, "value": value},
                )
            )
    return issues


def _check_unresolved_placeholders(text: str) -> list[QualityIssue]:
    unresolved = sorted(set(_PLACEHOLDER_RE.findall(text or "")))
    return [
        QualityIssue(
            code="UNRESOLVED_PLACEHOLDER",
            message=f"Unresolved placeholder '{name}'",
            severity="critical",
            stage="quality_gate",
            details={"placeholder": name},
        )
        for name in unresolved
    ]


def build_quality_report(
    *,
    data: dict[str, Any],
    required_fields: list[str] | None = None,
    date_fields: list[str] | None = None,
    numeric_fields: list[str] | None = None,
    rendered_text: str | None = None,
) -> QualityReport:
    issues: list[QualityIssue] = []
    issues.extend(_validate_required_fields(data, required_fields or []))
    issues.extend(_validate_value_types(data, date_fields or [], numeric_fields or []))
    if rendered_text:
        issues.extend(_check_unresolved_placeholders(rendered_text))

    critical_count = sum(1 for issue in issues if issue.severity == "critical")
    warning_count = sum(1 for issue in issues if issue.severity == "warning")
    release_blocked = critical_count > 0
    return QualityReport(
        status="failed" if release_blocked else "passed",
        release_blocked=release_blocked,
        summary={"critical": critical_count, "warning": warning_count, "total": len(issues)},
        issues=issues,
    )
