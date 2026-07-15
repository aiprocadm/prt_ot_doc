"""Unit: evaluator условий (table-driven, без БД)."""

from __future__ import annotations

import pytest

from app.modules.rules_engine.conditions import (
    ConditionsError,
    evaluate,
    evaluate_condition,
    validate_conditions,
)

PAYLOAD = {
    "tenant_id": "t1",
    "actor_id": "u1",
    "severity": "critical",
    "incident_type": "injury",
    "count": 17,
    "count_str": "17",
    "flag": True,
    "before": {"level": 12},
    "tags": ["a", "b"],
    "empty": None,
    "occurred_at": "2026-07-15T10:00:00+00:00",
}


@pytest.mark.parametrize(
    ("cond", "expected"),
    [
        ({"field": "severity", "op": "eq", "value": "critical"}, True),
        ({"field": "severity", "op": "eq", "value": "low"}, False),
        ({"field": "severity", "op": "ne", "value": "low"}, True),
        ({"field": "severity", "op": "in", "value": ["high", "critical"]}, True),
        ({"field": "severity", "op": "not_in", "value": ["high", "critical"]}, False),
        ({"field": "count", "op": "gt", "value": 15}, True),
        ({"field": "count_str", "op": "gt", "value": 15}, True),
        ({"field": "count", "op": "lte", "value": 17}, True),
        ({"field": "count", "op": "lt", "value": 17}, False),
        ({"field": "flag", "op": "gt", "value": 0}, False),
        ({"field": "before.level", "op": "gte", "value": 12}, True),
        ({"field": "severity", "op": "contains", "value": "CRIT"}, True),
        ({"field": "tags", "op": "contains", "value": "b"}, True),
        ({"field": "tags", "op": "contains", "value": "z"}, False),
        ({"field": "missing", "op": "eq", "value": "x"}, False),
        ({"field": "missing", "op": "exists"}, False),
        ({"field": "missing", "op": "exists", "value": False}, True),
        ({"field": "empty", "op": "exists"}, False),
        ({"field": "severity", "op": "exists"}, True),
        ({"field": "occurred_at", "op": "gte", "value": "2026-07-01T00:00:00+00:00"}, True),
    ],
)
def test_evaluate_condition(cond, expected):
    assert evaluate_condition(cond, PAYLOAD) is expected


def test_match_all_vs_any():
    conds = [
        {"field": "severity", "op": "eq", "value": "critical"},
        {"field": "count", "op": "gt", "value": 100},
    ]
    assert evaluate({"match": "all", "conditions": conds}, PAYLOAD) is False
    assert evaluate({"match": "any", "conditions": conds}, PAYLOAD) is True


def test_empty_conditions_match_everything():
    assert evaluate({}, PAYLOAD) is True
    assert evaluate(None, PAYLOAD) is True


@pytest.mark.parametrize(
    ("raw", "code"),
    [
        ([], "invalid_conditions"),
        ({"match": "some"}, "invalid_match"),
        ({"conditions": [{"field": "bad field!", "op": "eq"}]}, "invalid_condition_field"),
        ({"conditions": [{"field": "a", "op": "like"}]}, "invalid_condition_op"),
        ({"conditions": [{"field": "a", "op": "in", "value": "x"}]}, "invalid_condition_value"),
        (
            {"conditions": [{"field": "a", "op": "in", "value": list(range(51))}]},
            "invalid_condition_value",
        ),
        (
            {"conditions": [{"field": "a", "op": "eq", "value": 1}] * 21},
            "too_many_conditions",
        ),
    ],
)
def test_validate_conditions_errors(raw, code):
    with pytest.raises(ConditionsError) as exc:
        validate_conditions(raw)
    assert exc.value.code == code


def test_validate_known_fields():
    validate_conditions(
        {"conditions": [{"field": "severity", "op": "eq", "value": "x"}]},
        known_fields=frozenset({"severity"}),
    )
    with pytest.raises(ConditionsError) as exc:
        validate_conditions(
            {"conditions": [{"field": "bogus", "op": "eq", "value": "x"}]},
            known_fields=frozenset({"severity"}),
        )
    assert exc.value.code == "unknown_condition_field"


def test_dot_path_first_segment_validated():
    validate_conditions(
        {"conditions": [{"field": "before.level", "op": "gt", "value": 1}]},
        known_fields=frozenset({"before"}),
    )


def test_exists_with_non_bool_value_rejected():
    with pytest.raises(ConditionsError) as exc:
        validate_conditions({"conditions": [{"field": "a", "op": "exists", "value": "yes"}]})
    assert exc.value.code == "invalid_condition_value"
