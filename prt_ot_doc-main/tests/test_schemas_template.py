from __future__ import annotations

import pytest

from app.schemas.template import (
    MAX_METADATA_DEPTH,
    MAX_METADATA_KEY_LENGTH,
    MAX_METADATA_LIST_ITEMS,
    MAX_METADATA_STRING_LENGTH,
    MAX_METADATA_TOTAL_STRING_LENGTH,
    TemplateCreate,
)


def test_template_create_normalizes_fields() -> None:
    payload = TemplateCreate(
        name="  @@Safety  Plan!!  ",
        description="  Important procedures   ",
        metadata={
            "   Responsible Person   ": "  Ivan Ivanov  ",
            "items": ["  Gloves  ", 5],
        },
    )
    assert payload.name == "Safety Plan"
    assert payload.description == "Important procedures"
    assert payload.metadata == {
        "Responsible Person": "Ivan Ivanov",
        "items": ["Gloves", 5],
    }


def test_template_create_rejects_invalid_name() -> None:
    with pytest.raises(ValueError, match="name must contain"):
        TemplateCreate(name="   !!!   ", description=None, metadata={})


def test_template_create_rejects_invalid_metadata_types() -> None:
    with pytest.raises(ValueError, match="metadata values must be primitives"):
        TemplateCreate(name="Doc", description=None, metadata={"key": object()})


def test_template_create_enforces_string_length_limit() -> None:
    too_long = "x" * (MAX_METADATA_STRING_LENGTH + 1)
    with pytest.raises(ValueError, match="metadata strings cannot exceed"):
        TemplateCreate(name="Doc", description=None, metadata={"k": too_long})


def test_template_create_enforces_total_string_limit() -> None:
    chunk = "a" * MAX_METADATA_STRING_LENGTH
    items = (MAX_METADATA_TOTAL_STRING_LENGTH // MAX_METADATA_STRING_LENGTH) + 1
    metadata = {f"k{i}": chunk for i in range(items)}
    with pytest.raises(ValueError, match="metadata string values exceed"):
        TemplateCreate(name="Doc", description=None, metadata=metadata)


def test_template_create_enforces_nested_depth() -> None:
    nested: dict[str, object] = {}
    current = nested
    for _ in range(MAX_METADATA_DEPTH + 1):
        next_level: dict[str, object] = {}
        current["branch"] = next_level
        current = next_level
    with pytest.raises(ValueError, match="metadata nesting depth"):
        TemplateCreate(name="Doc", description=None, metadata=nested)


def test_template_create_limits_keys_and_lists() -> None:
    long_key = "a" * (MAX_METADATA_KEY_LENGTH + 1)
    with pytest.raises(ValueError, match="metadata keys cannot exceed"):
        TemplateCreate(name="Doc", description=None, metadata={long_key: "value"})

    metadata = {"list": [str(i) for i in range(MAX_METADATA_LIST_ITEMS + 1)]}
    with pytest.raises(ValueError, match="metadata lists cannot contain"):
        TemplateCreate(name="Doc", description=None, metadata=metadata)
