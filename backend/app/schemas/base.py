"""Shared schema base classes with timezone-aware serialization."""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict

from app.core.i18n import get_runtime_timezone

__all__ = ["BaseSchema", "serialize_datetime"]


def serialize_datetime(value: datetime) -> str:
    """Normalize datetimes to the configured runtime timezone."""

    tz = get_runtime_timezone()
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(tz).isoformat()


class BaseSchema(BaseModel):
    """Base Pydantic model applying consistent serialization defaults."""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        json_encoders={datetime: serialize_datetime},
    )
