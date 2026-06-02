"""Unit test for the native_enum() helper: it must produce an Enum that binds
the member .value (lowercase/CamelCase), not the member NAME."""
from __future__ import annotations

import enum

from app.models.base import native_enum


class _Color(str, enum.Enum):
    RED = "red"
    DARK_BLUE = "dark_blue"


def test_native_enum_binds_values_not_names() -> None:
    t = native_enum(_Color, name="color")
    assert list(t.enums) == ["red", "dark_blue"]      # .value, not NAME
    assert t.name == "color"
    assert t.enum_class is _Color


def test_native_enum_derives_name_when_omitted() -> None:
    t = native_enum(_Color)
    # SQLAlchemy derives the type name from the enum class when name is omitted.
    assert list(t.enums) == ["red", "dark_blue"]
