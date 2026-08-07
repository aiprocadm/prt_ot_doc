"""Профиль земляных работ (883н): валидация type_specific и печатная секция."""

from __future__ import annotations

import pytest

from app.domains.work_permits import profiles as p


def test_validate_accepts_valid_excavation():
    p.validate_type_specific(
        "excavation",
        {"utilities": ["power_cable", "water_sewer"], "shoring": "shield_bracing"},
    )


def test_validate_rejects_unknown_key():
    with pytest.raises(ValueError):
        p.validate_type_specific("excavation", {"gas_analysis": []})


def test_validate_rejects_bad_utility():
    with pytest.raises(ValueError):
        p.validate_type_specific("excavation", {"utilities": ["lava_tube"]})


def test_validate_rejects_bad_shoring():
    with pytest.raises(ValueError):
        p.validate_type_specific("excavation", {"shoring": "magic"})


def test_validate_accepts_empty():
    p.validate_type_specific("excavation", None)
    p.validate_type_specific("excavation", {})


def test_build_section_renders_shoring_and_utilities():
    section = p.build_structured_section(
        "excavation",
        safety_systems=None,
        type_specific={"utilities": ["power_cable"], "shoring": "shield_bracing"},
    )
    assert section is not None
    assert section.table is None
    flat = " ".join(f"{k}: {v}" for k, v in section.kv)
    assert "Крепление щитами" in flat
    assert "кабели" in flat.lower()


def test_build_section_none_when_empty():
    assert p.build_structured_section("excavation", safety_systems=None, type_specific={}) is None


def test_excavation_profile_structured_kind():
    assert p.profile_for("excavation").structured_kind == "excavation_safety"
