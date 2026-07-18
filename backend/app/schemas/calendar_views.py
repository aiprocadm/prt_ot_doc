"""Saved Smart Calendar view schemas (vNext-CAL-01 / Phase 4.1).

DTOs for CRUD on per-user filter presets. `payload` is intentionally
typed as a structured pydantic model (`SavedCalendarViewPayload`) so we
get validation at the API boundary, but the model column stores it as
opaque JSON — adding a new toggle in the future only requires extending
this schema, not a database migration.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field, field_validator

from app.schemas.base import BaseSchema

__all__ = [
    "SavedCalendarViewPayload",
    "SavedCalendarViewCreateRequest",
    "SavedCalendarViewUpdateRequest",
    "SavedCalendarView",
]


_ALLOWED_VIEWS = {"day", "week", "month", "year", "list"}
_ALLOWED_SOURCES = {
    "medical_exam",
    "ppe_issue",
    "permit",
    "training_session",
    "inspection",
    "compliance_deadline",
    "briefing_entry",
    "calendar_event",
}
_ALLOWED_SLA_BANDS = {"overdue", "critical", "warning", "ok"}
_ALLOWED_LOAD_DIMS = {"person", "site"}


class SavedCalendarViewPayload(BaseSchema):
    """Filter snapshot stored inside a saved view.

    Mirrors the URL query state used by `CalendarPage.tsx`. All fields
    are optional so a saved view can be partial (e.g. «only filter by
    site, leave everything else default»).
    """

    view: str | None = Field(default=None, description="Calendar view: day/week/month/year/list")
    sources: list[str] = Field(
        default_factory=list,
        description="Selected source-type chips; empty list ⇒ all sources",
    )
    person_id: str | None = Field(default=None, max_length=64)
    site_id: str | None = Field(default=None, max_length=64)
    include_fact: bool = False
    include_sla: bool = False
    sla_bands: list[str] = Field(
        default_factory=list,
        description="Selected SLA-band chips when include_sla is on",
    )
    include_load: bool = False
    load_dim: str | None = Field(
        default=None,
        description="Resource-load dimension when include_load is on: person/site",
    )

    @field_validator("view")
    @classmethod
    def _validate_view(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if value not in _ALLOWED_VIEWS:
            raise ValueError(f"view must be one of {sorted(_ALLOWED_VIEWS)!r}")
        return value

    @field_validator("sources")
    @classmethod
    def _validate_sources(cls, value: list[str]) -> list[str]:
        for source in value:
            if source not in _ALLOWED_SOURCES:
                raise ValueError(f"unknown source type: {source!r}")
        # Stable order, deduplicate.
        seen: dict[str, None] = {}
        for source in value:
            seen.setdefault(source, None)
        return list(seen)

    @field_validator("sla_bands")
    @classmethod
    def _validate_sla_bands(cls, value: list[str]) -> list[str]:
        for band in value:
            if band not in _ALLOWED_SLA_BANDS:
                raise ValueError(f"unknown sla_band: {band!r}")
        seen: dict[str, None] = {}
        for band in value:
            seen.setdefault(band, None)
        return list(seen)

    @field_validator("load_dim")
    @classmethod
    def _validate_load_dim(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if value not in _ALLOWED_LOAD_DIMS:
            raise ValueError(f"load_dim must be one of {sorted(_ALLOWED_LOAD_DIMS)!r}")
        return value


class SavedCalendarViewCreateRequest(BaseSchema):
    name: str = Field(min_length=1, max_length=128)
    payload: SavedCalendarViewPayload


class SavedCalendarViewUpdateRequest(BaseSchema):
    """Same shape as create — both name and payload are required.

    PATCH is implemented as «full replace» of the user-editable fields,
    which keeps the controller trivial and avoids merge-vs-replace
    ambiguity in JSON payload semantics.
    """

    name: str = Field(min_length=1, max_length=128)
    payload: SavedCalendarViewPayload


class SavedCalendarView(BaseSchema):
    id: str
    name: str
    payload: SavedCalendarViewPayload
    created_at: datetime
    updated_at: datetime
