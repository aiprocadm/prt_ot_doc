"""Чистый evaluator условий правил (без I/O).

Формат: {"match": "all"|"any", "conditions": [{"field","op","value"}]}.
``field`` — dot-путь по нормализованному payload события.
Оценка устойчива: отсутствующее поле / несравнимые типы → условие НЕ матчится
(исключений наружу нет); ``exists`` — единственный op, матчащийся на отсутствии.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

ALLOWED_OPS = frozenset(
    {"eq", "ne", "in", "not_in", "gt", "gte", "lt", "lte", "contains", "exists"}
)
ALLOWED_MATCH = frozenset({"all", "any"})
MAX_CONDITIONS = 20
MAX_IN_VALUES = 50

_FIELD_RE = re.compile(r"^[A-Za-z0-9_]+(\.[A-Za-z0-9_]+)*$")


class ConditionsError(ValueError):
    """Typed-ошибка валидации; code уходит в 422 API."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def validate_conditions(raw: Any, *, known_fields: frozenset[str] | None = None) -> None:
    """422-валидация структуры. ``known_fields`` — top-level поля payload-модели события
    (первый сегмент dot-пути обязан входить в них, если каталог передан)."""
    if not isinstance(raw, Mapping):
        raise ConditionsError("invalid_conditions", "conditions_json must be an object")
    match = raw.get("match", "all")
    if match not in ALLOWED_MATCH:
        raise ConditionsError("invalid_match", f"match must be one of {sorted(ALLOWED_MATCH)}")
    conditions = raw.get("conditions", [])
    if not isinstance(conditions, list):
        raise ConditionsError("invalid_conditions", "conditions must be a list")
    if len(conditions) > MAX_CONDITIONS:
        raise ConditionsError("too_many_conditions", f"at most {MAX_CONDITIONS} conditions")
    for idx, cond in enumerate(conditions):
        if not isinstance(cond, Mapping):
            raise ConditionsError("invalid_condition", f"condition #{idx} must be an object")
        field = cond.get("field")
        op = cond.get("op")
        if not isinstance(field, str) or not _FIELD_RE.match(field):
            raise ConditionsError("invalid_condition_field", f"condition #{idx}: bad field")
        if op not in ALLOWED_OPS:
            raise ConditionsError("invalid_condition_op", f"condition #{idx}: bad op {op!r}")
        if known_fields is not None and field.split(".", 1)[0] not in known_fields:
            raise ConditionsError(
                "unknown_condition_field",
                f"condition #{idx}: field {field!r} is not part of the event payload",
            )
        value = cond.get("value")
        if op in {"in", "not_in"}:
            if not isinstance(value, list) or len(value) > MAX_IN_VALUES:
                raise ConditionsError(
                    "invalid_condition_value",
                    f"condition #{idx}: {op} needs a list of <= {MAX_IN_VALUES} items",
                )
        if op == "exists" and value is not None and not isinstance(value, bool):
            raise ConditionsError(
                "invalid_condition_value", f"condition #{idx}: exists needs a bool value"
            )


def resolve_field(payload: Mapping[str, Any], path: str) -> tuple[bool, Any]:
    """(found, value) по dot-пути. Отсутствие любого сегмента → (False, None)."""
    current: Any = payload
    for segment in path.split("."):
        if not isinstance(current, Mapping) or segment not in current:
            return False, None
        current = current[segment]
    return True, current


def _as_decimal(value: Any) -> Decimal | None:
    if isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _loose_eq(actual: Any, expected: Any) -> bool:
    if actual == expected:
        return True
    a_num, e_num = _as_decimal(actual), _as_decimal(expected)
    if a_num is not None and e_num is not None:
        return a_num == e_num
    return False


def _compare(actual: Any, expected: Any, op: str) -> bool:
    a_num, e_num = _as_decimal(actual), _as_decimal(expected)
    if a_num is not None and e_num is not None:
        a, b = a_num, e_num
    elif isinstance(actual, str) and isinstance(expected, str):
        a, b = actual, expected  # ISO-даты сравниваются лексикографически корректно
    else:
        return False
    return {"gt": a > b, "gte": a >= b, "lt": a < b, "lte": a <= b}[op]


def evaluate_condition(cond: Mapping[str, Any], payload: Mapping[str, Any]) -> bool:
    field = str(cond.get("field", ""))
    op = str(cond.get("op", ""))
    expected = cond.get("value")
    found, actual = resolve_field(payload, field)
    if op == "exists":
        want = True if expected is None else bool(expected)
        return (found and actual is not None) == want
    if not found or actual is None:
        return False
    if op == "eq":
        return _loose_eq(actual, expected)
    if op == "ne":
        return not _loose_eq(actual, expected)
    if op == "in":
        return isinstance(expected, list) and any(_loose_eq(actual, v) for v in expected)
    if op == "not_in":
        return isinstance(expected, list) and not any(_loose_eq(actual, v) for v in expected)
    if op == "contains":
        if isinstance(actual, str):
            return isinstance(expected, str) and expected.lower() in actual.lower()
        if isinstance(actual, (list, tuple)):
            return any(_loose_eq(item, expected) for item in actual)
        return False
    if op in {"gt", "gte", "lt", "lte"}:
        return _compare(actual, expected, op)
    return False


def evaluate(conditions_json: Mapping[str, Any] | None, payload: Mapping[str, Any]) -> bool:
    """Пустые условия = матч любого события своего event_type."""
    raw = conditions_json or {}
    conditions = raw.get("conditions") or []
    if not conditions:
        return True
    results = (evaluate_condition(c, payload) for c in conditions)
    return any(results) if raw.get("match", "all") == "any" else all(results)
