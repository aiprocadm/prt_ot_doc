from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

DocumentStage = Literal[
    "validate_template",
    "render_docx",
    "apply_headers",
    "replace",
    "quality_gate",
    "convert_pdf",
    "send_for_approval",
    "sign",
    "send_edo",
    "archive",
]
Severity = Literal["critical", "warning"]


class QualityIssue(BaseModel):
    code: str
    message: str
    severity: Severity
    stage: DocumentStage
    details: dict[str, Any] = Field(default_factory=dict)


class QualityReport(BaseModel):
    status: Literal["passed", "failed"]
    release_blocked: bool
    summary: dict[str, int]
    issues: list[QualityIssue] = Field(default_factory=list)

