from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import isfinite
import re
from typing import Any

from pydantic import ConfigDict, Field, field_validator, model_validator

from app.schemas.base import BaseSchema, serialize_datetime

_NAME_ALLOWED_PATTERN = re.compile(r"[^\w\s\-.]")
_COLLAPSE_WHITESPACE = re.compile(r"\s+")

MAX_METADATA_TOP_LEVEL_KEYS = 200
MAX_METADATA_NESTED_KEYS = 500
MAX_METADATA_LIST_ITEMS = 200
MAX_METADATA_STRING_LENGTH = 2048
MAX_METADATA_TOTAL_STRING_LENGTH = 16_384
MAX_METADATA_DEPTH = 5
MAX_METADATA_KEY_LENGTH = 64


@dataclass(slots=True)
class _TraversalState:
    total_keys: int = 0
    total_string_length: int = 0

    def track_string(self, value: str) -> None:
        self.total_string_length += len(value)
        if self.total_string_length > MAX_METADATA_TOTAL_STRING_LENGTH:
            msg = (
                "metadata string values exceed the combined limit "
                f"of {MAX_METADATA_TOTAL_STRING_LENGTH} characters"
            )
            raise ValueError(msg)

    def track_keys(self, count: int) -> None:
        self.total_keys += count
        if self.total_keys > MAX_METADATA_NESTED_KEYS:
            msg = (
                "metadata cannot contain more than "
                f"{MAX_METADATA_NESTED_KEYS} total keys"
            )
            raise ValueError(msg)


def _sanitize_template_name(value: str) -> str:
    normalized = value.strip()
    normalized = _NAME_ALLOWED_PATTERN.sub(" ", normalized)
    normalized = _COLLAPSE_WHITESPACE.sub(" ", normalized)
    normalized = normalized.strip()
    if not normalized:
        raise ValueError("name must contain letters or digits")
    if not re.search(r"\w", normalized):
        raise ValueError("name must contain alphanumeric characters")
    if len(normalized) > 120:
        normalized = normalized[:120].rstrip()
    return normalized


def _validate_key(key: str) -> str:
    candidate = _COLLAPSE_WHITESPACE.sub(" ", key.strip())
    if not candidate:
        raise ValueError("metadata keys cannot be blank")
    if len(candidate) > MAX_METADATA_KEY_LENGTH:
        raise ValueError(
            f"metadata keys cannot exceed {MAX_METADATA_KEY_LENGTH} characters"
        )
    return candidate


def _validate_metadata_value(value: Any, *, depth: int, state: _TraversalState) -> Any:
    if depth > MAX_METADATA_DEPTH:
        raise ValueError(f"metadata nesting depth cannot exceed {MAX_METADATA_DEPTH}")

    if isinstance(value, dict):
        if len(value) > MAX_METADATA_TOP_LEVEL_KEYS:
            raise ValueError(
                f"metadata objects cannot contain more than {MAX_METADATA_TOP_LEVEL_KEYS} keys"
            )
        state.track_keys(len(value))
        return {
            _validate_key(k): _validate_metadata_value(v, depth=depth + 1, state=state)
            for k, v in value.items()
        }

    if isinstance(value, list):
        if len(value) > MAX_METADATA_LIST_ITEMS:
            raise ValueError(
                f"metadata lists cannot contain more than {MAX_METADATA_LIST_ITEMS} items"
            )
        return [
            _validate_metadata_value(item, depth=depth + 1, state=state)
            for item in value
        ]

    if isinstance(value, str):
        candidate = value.strip()
        if len(candidate) > MAX_METADATA_STRING_LENGTH:
            raise ValueError(
                f"metadata strings cannot exceed {MAX_METADATA_STRING_LENGTH} characters"
            )
        state.track_string(candidate)
        return candidate

    if isinstance(value, (int, bool)):
        return value

    if isinstance(value, float):
        if not isfinite(value):
            raise ValueError("metadata floats must be finite values")
        return value

    if value is None:
        return value

    raise ValueError("metadata values must be primitives, lists or dictionaries")


def _normalize_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    if len(metadata) > MAX_METADATA_TOP_LEVEL_KEYS:
        raise ValueError(
            f"metadata objects cannot contain more than {MAX_METADATA_TOP_LEVEL_KEYS} keys"
        )
    state = _TraversalState()
    state.track_keys(len(metadata))
    sanitized = {
        _validate_key(key): _validate_metadata_value(value, depth=1, state=state)
        for key, value in metadata.items()
    }
    return sanitized


class TemplateCreate(BaseSchema):
    name: str = Field(..., min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=255)
    metadata: dict[str, Any] = Field(default_factory=dict)
    model_config = ConfigDict(
        extra="forbid",
        frozen=False,
        from_attributes=True,
        populate_by_name=True,
        json_encoders={datetime: serialize_datetime},
    )

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return _sanitize_template_name(value)

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        candidate = value.strip()
        return candidate or None

    @model_validator(mode="after")
    def validate_metadata(self) -> TemplateCreate:
        self.metadata = _normalize_metadata(self.metadata)
        return self


__all__ = [
    "TemplateCreate",
    "MAX_METADATA_STRING_LENGTH",
    "MAX_METADATA_TOP_LEVEL_KEYS",
    "MAX_METADATA_DEPTH",
]
