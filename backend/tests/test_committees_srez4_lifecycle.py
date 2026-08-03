"""Unit: committees срез-4 lifecycle — настраиваемый порог кворума + приглашения."""

from __future__ import annotations

import pytest

from app.domains.committees.lifecycle import (
    MeetingTransitionError,
    ensure_can_invite,
    is_quorum,
)
from app.models.committees import MeetingStatus


class TestQuorumThreshold:
    def test_default_none_is_strict_majority(self):
        # прежнее правило: строго больше половины
        assert is_quorum(4, 3) is True
        assert is_quorum(4, 2) is False
        assert is_quorum(0, 0) is False

    def test_threshold_two_thirds(self):
        # 66%: 4 члена → нужно >= 2.64, т.е. 3 присутствующих
        assert is_quorum(4, 3, threshold_pct=66) is True
        assert is_quorum(4, 2, threshold_pct=66) is False

    def test_threshold_100_requires_everyone(self):
        assert is_quorum(5, 5, threshold_pct=100) is True
        assert is_quorum(5, 4, threshold_pct=100) is False

    def test_threshold_low_bar(self):
        # 25%: 4 члена → достаточно 1 присутствующего
        assert is_quorum(4, 1, threshold_pct=25) is True
        assert is_quorum(4, 0, threshold_pct=25) is False

    def test_threshold_exact_boundary_inclusive(self):
        # ровно на пороге — кворум есть (50% от 4 = 2)
        assert is_quorum(4, 2, threshold_pct=50) is True

    def test_threshold_with_zero_members(self):
        assert is_quorum(0, 0, threshold_pct=50) is False


class TestEnsureCanInvite:
    def test_planned_ok(self):
        ensure_can_invite(MeetingStatus.PLANNED)

    @pytest.mark.parametrize("status", [MeetingStatus.HELD, MeetingStatus.CANCELLED])
    def test_non_planned_rejected(self, status):
        with pytest.raises(MeetingTransitionError):
            ensure_can_invite(status)
