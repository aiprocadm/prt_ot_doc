"""Schemas for dashboard summary reporting."""

from __future__ import annotations

from app.schemas.base import BaseSchema


class DashboardTrainingSummary(BaseSchema):
    total: int
    overdue: int
    due_soon: int
    status: str


class DashboardSummary(BaseSchema):
    overdue_tasks: int
    critical_obligations: int
    incidents_open: int
    risks_total: int
    training: DashboardTrainingSummary
    generated_at: str


class DashboardTaskInboxItem(BaseSchema):
    id: str
    title: str
    owner_label: str | None = None
    due_at: str | None = None
    priority: str
    status: str
    overdue: bool = False
    entity_type: str | None = None
    entity_id: str | None = None


class DashboardDocumentInboxItem(BaseSchema):
    id: str
    title: str
    route_label: str
    status: str
    risk: str
    created_at: str
    template_code: str | None = None
    template_version: int | None = None


class DashboardReadinessSnapshot(BaseSchema):
    packages_total: int
    open_gaps: int
    critical_gaps: int
    latest_target_date: str | None = None
    readiness_score: int
    reasons: list[str]


class DashboardOperationalSnapshot(BaseSchema):
    tasks: list[DashboardTaskInboxItem]
    documents: list[DashboardDocumentInboxItem]
    readiness: DashboardReadinessSnapshot
    generated_at: str
