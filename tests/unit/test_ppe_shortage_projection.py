"""Pure shortage projection — no DB (P10-06)."""

from __future__ import annotations

from app.modules.ppe.stock import ShortageProjection, project_shortage


def test_above_threshold_not_below():
    p = project_shortage(on_hand=100, min_stock=20, avg_daily=1.0)
    assert p.below_threshold is False
    assert p.deficit == 0
    assert p.days_to_depletion == 100.0
    assert p.days_to_threshold == 80.0


def test_below_threshold_sets_deficit_and_zero_days_to_threshold():
    p = project_shortage(on_hand=5, min_stock=20, avg_daily=1.0)
    assert p.below_threshold is True
    assert p.deficit == 15
    assert p.days_to_depletion == 5.0
    assert p.days_to_threshold == 0.0


def test_at_threshold_is_not_below():
    p = project_shortage(on_hand=20, min_stock=20, avg_daily=2.0)
    assert p.below_threshold is False
    assert p.deficit == 0
    assert p.days_to_threshold == 0.0


def test_zero_consumption_gives_none_days():
    p = project_shortage(on_hand=5, min_stock=20, avg_daily=0.0)
    assert p.below_threshold is True
    assert p.deficit == 15
    assert p.days_to_depletion is None
    assert p.days_to_threshold is None


def test_zero_on_hand_below_with_zero_days():
    p = project_shortage(on_hand=0, min_stock=10, avg_daily=2.0)
    assert p.below_threshold is True
    assert p.deficit == 10
    assert p.days_to_depletion == 0.0


def test_min_stock_zero_never_below():
    p = project_shortage(on_hand=0, min_stock=0, avg_daily=1.0)
    assert p.below_threshold is False
    assert p.deficit == 0


def test_returns_frozen_dataclass():
    p = project_shortage(on_hand=1, min_stock=1, avg_daily=0.0)
    assert isinstance(p, ShortageProjection)
