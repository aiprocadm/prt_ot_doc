"""Профили видов работ: приказ, валидация type_specific, сборка печатной секции."""
from __future__ import annotations

import pytest

from app.domains.work_permits import lifecycle as lc
from app.domains.work_permits import profiles as pr
from app.domains.work_permits.print_form import StructuredSection


def test_registry_covers_all_work_types():
    assert set(pr.PROFILES) == set(lc.WORK_TYPES)


def test_legal_reference_per_type():
    assert "782н" in pr.legal_reference("height")
    assert "902н" in pr.legal_reference("confined_space")
    assert "903н" in pr.legal_reference("electrical")
    assert "1479" in pr.legal_reference("hot_work")


def test_validate_confined_accepts_valid_payload():
    pr.validate_type_specific("confined_space", {
        "gas_analysis": [{"parameter": "oxygen", "value": "20.9", "norm": "≥ 20"}],
        "ventilation": "forced",
    })


def test_validate_confined_rejects_unknown_key():
    with pytest.raises(ValueError):
        pr.validate_type_specific("confined_space", {"bogus": 1})


def test_validate_confined_rejects_bad_parameter():
    with pytest.raises(ValueError):
        pr.validate_type_specific("confined_space", {"gas_analysis": [{"parameter": "xx", "value": "1"}]})


def test_validate_confined_rejects_bad_ventilation():
    with pytest.raises(ValueError):
        pr.validate_type_specific("confined_space", {"ventilation": "turbo"})


def test_validate_none_profile_rejects_nonempty():
    with pytest.raises(ValueError):
        pr.validate_type_specific("electrical", {"gas_analysis": []})


def test_validate_height_rejects_type_specific():
    with pytest.raises(ValueError):
        pr.validate_type_specific("height", {"ventilation": "forced"})


def test_validate_allows_none_and_empty():
    pr.validate_type_specific("confined_space", None)
    pr.validate_type_specific("electrical", None)
    pr.validate_type_specific("confined_space", {})


def test_build_section_height_from_safety_systems():
    sec = pr.build_structured_section("height", safety_systems=["restraint", "fall_arrest"], type_specific=None)
    assert isinstance(sec, StructuredSection)
    assert "Удерживающие" in sec.kv[0][1] and "Страховочные" in sec.kv[0][1]
    assert sec.table is None


def test_build_section_confined_from_type_specific():
    sec = pr.build_structured_section(
        "confined_space", safety_systems=None,
        type_specific={"gas_analysis": [{"parameter": "oxygen", "value": "20.9", "norm": "≥ 20"}],
                       "ventilation": "forced"})
    assert isinstance(sec, StructuredSection)
    assert any("Вентиляция" == k for k, _ in sec.kv)
    assert sec.table is not None and sec.table.rows[0][0] == "Кислород (O₂), %"


def test_build_section_none_profile_returns_none():
    assert pr.build_structured_section("electrical", safety_systems=None, type_specific=None) is None
