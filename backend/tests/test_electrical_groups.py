"""Группы по электробезопасности (903н): юнит-тесты чистого домена.

Покрываем: current_group, meets_minimum, readiness.
"""
from __future__ import annotations

from datetime import date

import pytest

from app.domains.work_permits import electrical_groups as eg


# ---------------------------------------------------------------------------
# current_group
# ---------------------------------------------------------------------------

class TestCurrentGroup:
    def test_returns_highest_of_multiple(self):
        quals = [
            {"kind": "electrical_safety_group", "level": "III"},
            {"kind": "electrical_safety_group", "level": "IV"},
        ]
        assert eg.current_group(quals, date(2026, 6, 23)) == "IV"

    def test_expired_entry_excluded(self):
        quals = [
            {"kind": "electrical_safety_group", "level": "IV", "valid_until": "2025-12-31"},
            {"kind": "electrical_safety_group", "level": "II"},
        ]
        # IV истекла, должна остаться II
        assert eg.current_group(quals, date(2026, 6, 23)) == "II"

    def test_no_valid_until_always_valid(self):
        quals = [
            {"kind": "electrical_safety_group", "level": "III"},
        ]
        # нет valid_until — действует всегда
        assert eg.current_group(quals, date(2099, 1, 1)) == "III"

    def test_valid_until_exactly_today_is_expired(self):
        """valid_until < as_of исключает; равный today НЕ исключает (граница)."""
        quals = [
            {"kind": "electrical_safety_group", "level": "III", "valid_until": "2026-06-23"},
        ]
        # valid_until == as_of → НЕ истекла (vu < as_of = False)
        assert eg.current_group(quals, date(2026, 6, 23)) == "III"

    def test_expired_before_today_excluded(self):
        quals = [
            {"kind": "electrical_safety_group", "level": "V", "valid_until": "2026-06-22"},
        ]
        assert eg.current_group(quals, date(2026, 6, 23)) is None

    def test_empty_list_returns_none(self):
        assert eg.current_group([], date(2026, 6, 23)) is None

    def test_none_list_returns_none(self):
        assert eg.current_group(None, date(2026, 6, 23)) is None

    def test_wrong_kind_ignored(self):
        quals = [
            {"kind": "training", "level": "V"},
            {"kind": "electrical_safety_group", "level": "II"},
        ]
        assert eg.current_group(quals, date(2026, 6, 23)) == "II"

    def test_all_wrong_kind_returns_none(self):
        quals = [
            {"kind": "training", "level": "IV"},
        ]
        assert eg.current_group(quals, date(2026, 6, 23)) is None

    def test_unknown_level_ignored(self):
        quals = [
            {"kind": "electrical_safety_group", "level": "SUPER"},
            {"kind": "electrical_safety_group", "level": "II"},
        ]
        assert eg.current_group(quals, date(2026, 6, 23)) == "II"

    def test_all_unknown_level_returns_none(self):
        quals = [
            {"kind": "electrical_safety_group", "level": "SUPER"},
        ]
        assert eg.current_group(quals, date(2026, 6, 23)) is None


# ---------------------------------------------------------------------------
# meets_minimum
# ---------------------------------------------------------------------------

class TestMeetsMinimum:
    def test_foreman_with_III_meets(self):
        assert eg.meets_minimum("III", "foreman") is True

    def test_foreman_with_II_fails(self):
        assert eg.meets_minimum("II", "foreman") is False

    def test_foreman_with_IV_meets(self):
        assert eg.meets_minimum("IV", "foreman") is True

    def test_issuer_requires_IV(self):
        assert eg.meets_minimum("III", "issuer") is False
        assert eg.meets_minimum("IV", "issuer") is True

    def test_unknown_role_always_true(self):
        assert eg.meets_minimum("I", "unknown_role") is True
        assert eg.meets_minimum(None, "unknown_role") is True

    def test_none_group_with_required_role_fails(self):
        assert eg.meets_minimum(None, "foreman") is False

    def test_none_group_with_no_requirement_true(self):
        assert eg.meets_minimum(None, "observer_nonexistent") is True

    def test_unknown_level_fails_when_role_requires(self):
        assert eg.meets_minimum("SUPER", "foreman") is False


# ---------------------------------------------------------------------------
# readiness
# ---------------------------------------------------------------------------

class TestReadiness:
    def test_all_sufficient(self):
        members = [
            {"person_id": "p1", "role": "foreman", "group": "III"},
            {"person_id": "p2", "role": "member", "group": "III"},
        ]
        result = eg.readiness(members)
        assert result["ok"] is True
        assert result["insufficient"] == []

    def test_one_foreman_insufficient(self):
        members = [
            {"person_id": "p1", "role": "foreman", "group": "II"},
            {"person_id": "p2", "role": "member", "group": "III"},
        ]
        result = eg.readiness(members)
        assert result["ok"] is False
        assert len(result["insufficient"]) == 1
        item = result["insufficient"][0]
        assert item["person_id"] == "p1"
        assert item["role"] == "foreman"
        assert item["group"] == "II"
        assert item["required"] == "III"

    def test_empty_members(self):
        result = eg.readiness([])
        assert result["ok"] is True
        assert result["insufficient"] == []

    def test_multiple_insufficient(self):
        members = [
            {"person_id": "p1", "role": "foreman", "group": "II"},
            {"person_id": "p2", "role": "issuer", "group": "III"},
        ]
        result = eg.readiness(members)
        assert result["ok"] is False
        assert len(result["insufficient"]) == 2

    def test_unknown_role_not_in_insufficient(self):
        members = [
            {"person_id": "p1", "role": "unknown_role", "group": "I"},
        ]
        result = eg.readiness(members)
        assert result["ok"] is True
        assert result["insufficient"] == []

    def test_none_group_foreman_insufficient(self):
        members = [
            {"person_id": "p1", "role": "foreman", "group": None},
        ]
        result = eg.readiness(members)
        assert result["ok"] is False
        assert result["insufficient"][0]["group"] is None
        assert result["insufficient"][0]["required"] == "III"


# ---------------------------------------------------------------------------
# role_min (voltage_level)
# ---------------------------------------------------------------------------

class TestRoleMin:
    def test_foreman_gt_1000_requires_IV(self):
        assert eg.role_min("foreman", "gt_1000") == "IV"

    def test_foreman_le_1000_requires_III(self):
        assert eg.role_min("foreman", "le_1000") == "III"

    def test_foreman_none_requires_III(self):
        assert eg.role_min("foreman", None) == "III"

    def test_supervisor_gt_1000_requires_V(self):
        assert eg.role_min("supervisor", "gt_1000") == "V"


# ---------------------------------------------------------------------------
# meets_minimum (voltage_level)
# ---------------------------------------------------------------------------

class TestMeetsMinimumVoltage:
    def test_foreman_III_gt_1000_fails(self):
        assert eg.meets_minimum("III", "foreman", "gt_1000") is False

    def test_foreman_IV_gt_1000_meets(self):
        assert eg.meets_minimum("IV", "foreman", "gt_1000") is True

    def test_supervisor_IV_gt_1000_fails(self):
        assert eg.meets_minimum("IV", "supervisor", "gt_1000") is False

    def test_foreman_III_le_1000_meets(self):
        assert eg.meets_minimum("III", "foreman", "le_1000") is True


# ---------------------------------------------------------------------------
# readiness (voltage_level)
# ---------------------------------------------------------------------------

class TestReadinessVoltage:
    def test_foreman_III_gt_1000_insufficient(self):
        members = [{"person_id": "p", "role": "foreman", "group": "III"}]
        result = eg.readiness(members, "gt_1000")
        assert result["ok"] is False
        assert result["insufficient"][0]["required"] == "IV"

    def test_foreman_III_no_voltage_ok(self):
        members = [{"person_id": "p", "role": "foreman", "group": "III"}]
        result = eg.readiness(members, None)
        assert result["ok"] is True
