"""Operational dashboard response schemas."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class AlertSeverity(str, Enum):
    """Alert severity levels."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class AlertCategory(str, Enum):
    """Alert categories."""

    OVERDUE = "overdue"
    BLOCKED_APPROVAL = "blocked_approval"
    INTEGRATION_ERROR = "integration_error"
    HIGH_RISK = "high_risk"
    HEALTH_WARNING = "health_warning"
    UNASSIGNED_TASK = "unassigned_task"
    DATA_QUALITY = "data_quality"
    COMMITTEE_TASK = "committee_task"


class AlertItem(BaseModel):
    """Single alert in operational dashboard."""

    id: str = Field(..., description="Unique alert ID")
    category: AlertCategory = Field(..., description="Alert category")
    severity: AlertSeverity = Field(..., description="Alert severity")
    title: str = Field(..., description="Alert title")
    description: str | None = Field(None, description="Detailed description")
    count: int = Field(default=1, description="Number of affected items")
    affected_entity_type: str | None = Field(
        None, description="Type of affected entity (document, employee, site, etc.)"
    )
    affected_entity_id: str | None = Field(None, description="ID of affected entity")
    action_url: str | None = Field(None, description="URL to take action on this alert")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: datetime | None = Field(None, description="When alert becomes resolved")


class OperationalDashboardResponse(BaseModel):
    """Operational dashboard response with all critical alerts."""

    tenant_id: str = Field(..., description="Tenant ID")
    status: str = Field(
        ...,
        description="Overall status: ok (no critical alerts), "
        "warning (high/medium alerts), critical (critical alerts)",
    )
    alerts: list[AlertItem] = Field(default_factory=list, description="List of alerts")
    alert_count: dict[AlertSeverity, int] = Field(
        default_factory=dict, description="Count of alerts by severity"
    )
    health_status: str | None = Field(
        None, description="Overall tenant health status from health checks"
    )
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    def model_dump(self, **kwargs) -> dict:
        """Override to ensure enums are serialized as strings."""
        data = super().model_dump(**kwargs)
        if "alert_count" in data:
            data["alert_count"] = {
                k.value if isinstance(k, AlertSeverity) else k: v
                for k, v in data.get("alert_count", {}).items()
            }
        return data
