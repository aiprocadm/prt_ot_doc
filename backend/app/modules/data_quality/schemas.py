"""Data quality check schemas and DTOs."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class IssueType(str, Enum):
    """Data quality issue types."""

    MISSING_FIELD = "missing_field"
    BROKEN_RELATIONSHIP = "broken_relationship"
    EXPIRED_RECORD = "expired_record"
    DUPLICATE = "duplicate"
    INVALID_VALUE = "invalid_value"
    DATA_MISMATCH = "data_mismatch"


class IssueSeverity(str, Enum):
    """Issue severity levels."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class DataQualityIssue(BaseModel):
    """Single data quality issue."""

    id: str = Field(..., description="Unique issue ID")
    issue_type: IssueType = Field(..., description="Type of data quality issue")
    severity: IssueSeverity = Field(..., description="Severity level")
    title: str = Field(..., description="Short description")
    description: str | None = Field(None, description="Detailed explanation")
    affected_entity_type: str = Field(..., description="Type of affected entity (employee, site, document, etc.)")
    affected_entity_id: str = Field(..., description="ID of affected entity")
    affected_entity_name: str | None = Field(None, description="Human-readable name")
    additional_info: dict[str, Any] = Field(default_factory=dict, description="Extra context")
    found_at: datetime = Field(default_factory=datetime.utcnow)


class DataQualityCheckResult(BaseModel):
    """Result of a single data quality check."""

    rule_name: str = Field(..., description="Name of the rule that ran")
    rule_description: str = Field(..., description="Human-readable rule description")
    total_checked: int = Field(..., description="Total entities checked")
    issues_found: int = Field(..., description="Number of issues found")
    issues: list[DataQualityIssue] = Field(default_factory=list, description="List of issues")
    execution_time_ms: float = Field(..., description="Execution time in milliseconds")


class DataQualityReport(BaseModel):
    """Comprehensive data quality report."""

    tenant_id: str = Field(..., description="Tenant ID")
    completeness_percent: float = Field(..., description="Data completeness percentage (0-100)")
    total_issues: int = Field(..., description="Total number of issues found")
    critical_issues: int = Field(..., description="Count of critical issues")
    high_issues: int = Field(..., description="Count of high severity issues")
    medium_issues: int = Field(..., description="Count of medium severity issues")
    low_issues: int = Field(..., description="Count of low severity issues")
    issue_breakdown: dict[str, int] = Field(default_factory=dict, description="Issues by type")
    entity_breakdown: dict[str, int] = Field(default_factory=dict, description="Issues by entity type")
    issues: list[DataQualityIssue] = Field(default_factory=list, description="Top issues")
    check_results: list[DataQualityCheckResult] = Field(default_factory=list, description="Individual rule results")
    generated_at: datetime = Field(default_factory=datetime.utcnow)
