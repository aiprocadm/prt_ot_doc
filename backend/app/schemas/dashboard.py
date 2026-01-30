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
