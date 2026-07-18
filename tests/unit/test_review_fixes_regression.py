"""Regression tests for pure-function bugs found in the broad review sweep.

- apply_quiet_hours: a same-day (non-overnight) quiet window must not delay a
  notification by ~24h (it previously bumped to the NEXT day's end-time).
- RiskCalculationService._pick_level: a residual score below the lowest rule band
  must map to the lowest level, not to "critical".
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.modules.risk.services import RiskCalculationService
from app.services.notifications import apply_quiet_hours


class TestApplyQuietHours:
    def test_same_day_window_shifts_to_end_of_same_day(self):
        # 00:00-08:00 is a normal daytime window (from < to). A 03:00 notification
        # must be released at 08:00 the SAME day, not 08:00 tomorrow.
        sched = datetime(2026, 7, 8, 3, 0, tzinfo=timezone.utc)
        out = apply_quiet_hours(sched, {"from": "00:00", "to": "08:00", "tz": "UTC"})
        assert out == datetime(2026, 7, 8, 8, 0, tzinfo=timezone.utc)

    def test_overnight_window_evening_shifts_to_next_morning(self):
        # 22:00-08:00 overnight window; 23:00 -> next day 08:00.
        sched = datetime(2026, 7, 8, 23, 0, tzinfo=timezone.utc)
        out = apply_quiet_hours(sched, {"from": "22:00", "to": "08:00", "tz": "UTC"})
        assert out == datetime(2026, 7, 9, 8, 0, tzinfo=timezone.utc)

    def test_overnight_window_early_morning_shifts_to_same_day(self):
        # 22:00-08:00 overnight window; 03:00 -> same day 08:00.
        sched = datetime(2026, 7, 8, 3, 0, tzinfo=timezone.utc)
        out = apply_quiet_hours(sched, {"from": "22:00", "to": "08:00", "tz": "UTC"})
        assert out == datetime(2026, 7, 8, 8, 0, tzinfo=timezone.utc)

    def test_outside_window_unchanged(self):
        sched = datetime(2026, 7, 8, 12, 0, tzinfo=timezone.utc)
        out = apply_quiet_hours(sched, {"from": "00:00", "to": "08:00", "tz": "UTC"})
        assert out == sched


class TestPickLevel:
    RULES = [
        {"min": 1, "max": 4, "level": "low"},
        {"min": 5, "max": 12, "level": "medium"},
        {"min": 13, "max": 25, "level": "high"},
    ]

    def test_within_range(self):
        assert RiskCalculationService._pick_level(3, self.RULES) == "low"
        assert RiskCalculationService._pick_level(10, self.RULES) == "medium"
        assert RiskCalculationService._pick_level(20, self.RULES) == "high"

    def test_below_lowest_band_returns_lowest_not_critical(self):
        # A fully-mitigated residual (0) sits below the lowest band -> "low", not "critical".
        assert RiskCalculationService._pick_level(0, self.RULES) == "low"

    def test_above_highest_band_returns_highest(self):
        assert RiskCalculationService._pick_level(99, self.RULES) == "high"

    def test_no_rules_defaults_to_critical(self):
        assert RiskCalculationService._pick_level(0, []) == "critical"
