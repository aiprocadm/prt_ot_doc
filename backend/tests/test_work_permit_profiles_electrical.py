"""Профиль электроустановок (903н): валидация type_specific и печатная секция."""
from __future__ import annotations

import pytest

from app.domains.work_permits import profiles as p


def test_validate_accepts_valid_electrical():
    p.validate_type_specific(
        "electrical",
        {"technical_measures": ["disconnect", "grounding"], "voltage_condition": "de_energized"},
    )  # не бросает


def test_validate_rejects_unknown_key():
    with pytest.raises(ValueError):
        p.validate_type_specific("electrical", {"gas_analysis": []})


def test_validate_rejects_bad_measure():
    with pytest.raises(ValueError):
        p.validate_type_specific("electrical", {"technical_measures": ["laser"]})


def test_validate_rejects_bad_voltage_condition():
    with pytest.raises(ValueError):
        p.validate_type_specific("electrical", {"voltage_condition": "underwater"})


def test_validate_accepts_empty():
    p.validate_type_specific("electrical", None)
    p.validate_type_specific("electrical", {})


def test_build_section_renders_condition_and_measures():
    section = p.build_structured_section(
        "electrical",
        safety_systems=None,
        type_specific={"technical_measures": ["disconnect", "grounding"], "voltage_condition": "de_energized"},
    )
    assert section is not None
    assert section.table is None
    flat = " ".join(f"{k}: {v}" for k, v in section.kv)
    assert "Со снятием напряжения" in flat
    assert "заземление" in flat.lower()


def test_build_section_none_when_empty():
    assert p.build_structured_section("electrical", safety_systems=None, type_specific={}) is None


def test_electrical_profile_structured_kind():
    assert p.profile_for("electrical").structured_kind == "electrical_safety"


# ---------------------------------------------------------------------------
# Task 2 — voltage_level в профиле электроустановок
# ---------------------------------------------------------------------------

def test_validate_accepts_gt_1000():
    """voltage_level='gt_1000' допустим в type_specific."""
    p.validate_type_specific("electrical", {"voltage_level": "gt_1000"})  # не бросает


def test_validate_rejects_bad_voltage_level():
    """Недопустимый voltage_level вызывает ValueError."""
    with pytest.raises(ValueError, match="voltage_level"):
        p.validate_type_specific("electrical", {"voltage_level": "bad"})


def test_validate_accepts_le_1000_with_measures():
    """voltage_level='le_1000' совместим с technical_measures."""
    p.validate_type_specific(
        "electrical",
        {"voltage_level": "le_1000", "technical_measures": ["disconnect"]},
    )  # не бросает


def test_build_section_renders_voltage_level():
    """build_structured_section с voltage_level='gt_1000' → секция содержит «Класс напряжения» и «Выше 1000 В»."""
    section = p.build_structured_section(
        "electrical",
        safety_systems=None,
        type_specific={"voltage_level": "gt_1000"},
    )
    assert section is not None
    flat = " ".join(f"{k}: {v}" for k, v in section.kv)
    assert "Класс напряжения" in flat
    assert "Выше 1000 В" in flat
