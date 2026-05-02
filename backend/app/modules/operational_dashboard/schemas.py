"""Schemas for operational dashboard (Command Center)."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class AlertItem(BaseModel):
    """Single alert in command center."""

    id: str = Field(..., description="Alert ID")
    type: str = Field(
        ..., description="Alert type: overdue, approval_blocked, integration_error, health_degraded"
    )
    severity: str = Field(
        ..., description="Severity: critical, high, medium, low"
    )
    title: str = Field(..., description="Alert title")
    description: str | None = Field(None, description="Alert details")
    entity_type: str | None = Field(None, description="Related entity type: task, document, site, training, etc.")
    entity_id: str | None = Field(None, description="Related entity ID")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    action_url: str | None = Field(None, description="URL to drill into this alert")


class OperationalDashboardMetrics(BaseModel):
    """High-level metrics for operational dashboard."""

    overdue_items: int = Field(0, description="Count of overdue tasks/items")
    blocked_approvals: int = Field(0, description="Count of documents blocked in approval")
    critical_alerts: int = Field(0, description="Count of critical severity alerts")
    degraded_services: int = Field(0, description="Count of degraded health checks")
    unassigned_tasks: int = Field(0, description="Count of unassigned tasks")


class OperationalDashboardResponse(BaseModel):
    """Comprehensive operational dashboard response (Phase 2.1)."""

    tenant_id: str = Field(..., description="Tenant ID")
    status: str = Field(
        default="ok",
        description="Overall status: ok, degraded, critical",
    )
    metrics: OperationalDashboardMetrics = Field(
        default_factory=OperationalDashboardMetrics,
        description="High-level metrics",
    )
    alerts: list[AlertItem] = Field(
        default_factory=list,
        description="List of critical alerts (limited to top 20)",
    )
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    last_update: datetime | None = Field(None, description="Last update timestamp from any module")
