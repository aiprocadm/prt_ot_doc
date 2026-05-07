"""Smart Calendar aggregate schemas (vNext-CAL-01 / Phase 4.1).

Read-only DTOs for `/api/v1/calendar/events` aggregator output.
Each event is normalized into a single shape regardless of source module
(MedicalExam, PPEIssue, Permit, TrainingSession, Inspection,
ComplianceDeadline, BriefingEntry) so the UI can render a unified timeline
without per-source branches.

Notes
-----
* Source-specific identifiers (e.g. `permit_type`, `exam_type`) are
  preserved in `extra` rather than promoted to top-level fields, keeping
  the wire contract stable as new sources are added.
* `is_overdue` is computed server-side using the same now() the rest of
  the request sees; clients should not recompute from `starts_at` alone.
* `status` is a free-form string mirrored from the source row — UI is
  expected to render with a fallback label map (the same pattern as the
  Employee Card).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from app.schemas.base import BaseSchema

__all__ = [
    "CalendarEventItem",
    "CalendarEventsResponse",
    "CalendarSourceCount",
]


class CalendarEventItem(BaseSchema):
    """Single normalized calendar event from any source module."""

    id: str = Field(
        description="Composite identifier `<source_type>:<source_id>` — stable across requests",
    )
    source_type: str = Field(
        description=(
            "Source module key: `medical_exam`, `ppe_issue`, `permit`, "
            "`training_session`, `inspection`, `compliance_deadline`, "
            "`briefing_entry`, `calendar_event`"
        )
    )
    source_id: str = Field(description="Primary key in the source table")
    title: str = Field(description="Human-readable summary, ru-localized where possible")
    starts_at: datetime = Field(description="Event start in UTC")
    ends_at: datetime | None = Field(
        default=None,
        description="Event end in UTC (None for point-in-time events)",
    )
    status: str | None = Field(
        default=None,
        description="Source-specific status (e.g. `active`, `expired`, `planned`, `signed`)",
    )
    is_overdue: bool = Field(
        default=False,
        description="True if the event is past-due according to source-specific semantics",
    )
    person_id: str | None = None
    site_id: str | None = None
    company_id: str | None = None
    assigned_user_id: str | None = None
    extra: dict[str, Any] = Field(
        default_factory=dict,
        description="Source-specific fields (permit_type, exam_type, etc.)",
    )


class CalendarSourceCount(BaseSchema):
    """Per-source aggregate counters returned alongside items."""

    source_type: str
    count: int
    overdue_count: int = 0


class CalendarEventsResponse(BaseSchema):
    """Top-level aggregated response."""

    generated_at: datetime
    range_from: datetime | None = None
    range_to: datetime | None = None
    total: int
    overdue_count: int = 0
    by_source: list[CalendarSourceCount] = Field(default_factory=list)
    items: list[CalendarEventItem] = Field(default_factory=list)
