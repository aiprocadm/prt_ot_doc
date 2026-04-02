"""Schemas for obligation summary reporting."""

from __future__ import annotations

from app.schemas.base import BaseSchema


class ObligationSummaryItem(BaseSchema):
    entity_type: str | None
    total: int
    overdue: int


class ObligationSummary(BaseSchema):
    items: list[ObligationSummaryItem]
    total: int
    overdue: int
