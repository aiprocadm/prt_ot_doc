"""Pure-function unit tests for СОУТ norm-suggestion engine (срез-3)."""
from __future__ import annotations

from types import SimpleNamespace

from app.domains.sout.suggestions import build_ppe_norm_suggestions
from app.models.sout import SoutClass


def _factor(hazard_id, name="Шум", code="4.50", cls=SoutClass.HARMFUL_3_1):
    return SimpleNamespace(hazard_id=hazard_id, name=name, code=code, measured_class=cls)


def test_ppe_suggestion_for_linked_pair_without_norm() -> None:
    out = build_ppe_norm_suggestions(
        position_id="pos-1",
        factors=[_factor("haz-1")],
        hazard_titles={"haz-1": "Шум"},
        existing_norm_pairs=set(),
    )
    assert len(out) == 1
    s = out[0]
    assert (s.position_id, s.hazard_id) == ("pos-1", "haz-1")
    assert s.hazard_title == "Шум"
    assert "Шум" in s.reason


def test_ppe_dedup_when_norm_exists_for_pair() -> None:
    out = build_ppe_norm_suggestions(
        position_id="pos-1",
        factors=[_factor("haz-1")],
        hazard_titles={"haz-1": "Шум"},
        existing_norm_pairs={("pos-1", "haz-1")},
    )
    assert out == []


def test_ppe_empty_when_workplace_unlinked() -> None:
    out = build_ppe_norm_suggestions(
        position_id=None,
        factors=[_factor("haz-1")],
        hazard_titles={"haz-1": "Шум"},
        existing_norm_pairs=set(),
    )
    assert out == []


def test_ppe_skips_factor_without_hazard_link() -> None:
    out = build_ppe_norm_suggestions(
        position_id="pos-1",
        factors=[_factor(None)],
        hazard_titles={},
        existing_norm_pairs=set(),
    )
    assert out == []


def test_ppe_collapses_two_factors_on_same_hazard() -> None:
    out = build_ppe_norm_suggestions(
        position_id="pos-1",
        factors=[_factor("haz-1", name="Шум"), _factor("haz-1", name="Вибрация")],
        hazard_titles={"haz-1": "Физический"},
        existing_norm_pairs=set(),
    )
    assert len(out) == 1
