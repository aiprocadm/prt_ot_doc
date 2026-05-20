"""Phase 5.1 — Template Variable Inspector (vNext-DOC-02).

Tests cover the pure inspector function that builds a "used vs declared"
projection from a template version's parsed placeholder_index and its
required_fields_schema. The function is intentionally side-effect free so
the API layer (GET /api/v1/templates/{tid}/versions/{vid}/variables) is
the only IO surface.
"""

from __future__ import annotations

from app.modules.templates import inspect_template_variables


def test_empty_inputs_return_zero_state() -> None:
    report = inspect_template_variables(
        placeholder_index=None,
        required_fields_schema=None,
    )
    assert report["used"] == []
    assert report["loops"] == []
    assert report["conditions"] == []
    assert report["declared_required"] == []
    assert report["declared_available"] == []
    assert report["coverage"] == {
        "used_undeclared": [],
        "declared_unused": [],
        "used_count": 0,
        "declared_count": 0,
    }


def test_used_fields_pass_through_and_counted_by_root() -> None:
    report = inspect_template_variables(
        placeholder_index={
            "fields": [
                {"name": "person.name.first", "occurrences": 2, "locations": []},
                {"name": "person.name.last", "occurrences": 1, "locations": []},
                {"name": "company.short_name", "occurrences": 1, "locations": []},
            ],
            "loops": [],
            "conditions": [],
        },
        required_fields_schema=None,
    )
    assert [u["name"] for u in report["used"]] == [
        "person.name.first",
        "person.name.last",
        "company.short_name",
    ]
    assert report["coverage"]["used_count"] == 2  # person, company


def test_loop_variables_are_excluded_from_used_roots() -> None:
    report = inspect_template_variables(
        placeholder_index={
            "fields": [
                {"name": "item.qty", "occurrences": 1, "locations": []},
                {"name": "items", "occurrences": 1, "locations": []},
            ],
            "loops": [{"var": "item", "iter": "items", "locations": []}],
            "conditions": [],
        },
        required_fields_schema={"required": [], "properties": {"items": {}}},
    )
    assert report["coverage"]["used_undeclared"] == []
    assert report["coverage"]["used_count"] == 1  # only "items"


def test_used_undeclared_only_set_when_schema_advertises_properties() -> None:
    no_schema = inspect_template_variables(
        placeholder_index={
            "fields": [{"name": "mystery.id", "occurrences": 1, "locations": []}],
            "loops": [],
            "conditions": [],
        },
        required_fields_schema={},
    )
    # No `properties` key → cannot decide what's known, so skip.
    assert no_schema["coverage"]["used_undeclared"] == []

    with_schema = inspect_template_variables(
        placeholder_index={
            "fields": [
                {"name": "mystery.id", "occurrences": 1, "locations": []},
                {"name": "person.name", "occurrences": 1, "locations": []},
            ],
            "loops": [],
            "conditions": [],
        },
        required_fields_schema={
            "required": ["person"],
            "properties": {"person": {}, "company": {}},
        },
    )
    assert with_schema["coverage"]["used_undeclared"] == ["mystery"]


def test_declared_unused_emerges_when_required_field_is_not_used_in_template() -> None:
    report = inspect_template_variables(
        placeholder_index={
            "fields": [{"name": "person.name", "occurrences": 1, "locations": []}],
            "loops": [],
            "conditions": [],
        },
        required_fields_schema={
            "required": ["person", "sign_date"],
            "properties": {"person": {}, "sign_date": {}},
        },
    )
    assert report["declared_required"] == ["person", "sign_date"]
    assert report["declared_available"] == ["person", "sign_date"]
    assert report["coverage"]["declared_unused"] == ["sign_date"]


def test_invalid_required_entries_are_dropped() -> None:
    report = inspect_template_variables(
        placeholder_index=None,
        required_fields_schema={
            "required": ["valid_name", "", None, 123, {"oops": True}],
            "properties": {"valid_name": {}, "ignored_obj": {}},
        },
    )
    assert report["declared_required"] == ["valid_name"]
    # properties keys are sorted; only string keys retained
    assert report["declared_available"] == ["ignored_obj", "valid_name"]


def test_coverage_counts_reflect_only_string_property_keys() -> None:
    report = inspect_template_variables(
        placeholder_index={
            "fields": [
                {"name": "person", "occurrences": 1, "locations": []},
                {"name": "company.tin", "occurrences": 2, "locations": []},
            ],
            "loops": [],
            "conditions": [],
        },
        required_fields_schema={
            "required": ["person"],
            "properties": {"person": {}, "company": {}, "site": {}},
        },
    )
    assert report["coverage"] == {
        "used_undeclared": [],
        "declared_unused": [],
        "used_count": 2,
        "declared_count": 3,
    }


def test_loops_and_conditions_passed_through_unchanged() -> None:
    loops = [{"var": "x", "iter": "items", "locations": [{"source": "word/document.xml", "offset": 0}]}]
    conditions = [
        {"expr": "person.active", "locations": [{"source": "word/document.xml", "offset": 0}]}
    ]
    report = inspect_template_variables(
        placeholder_index={"fields": [], "loops": loops, "conditions": conditions},
        required_fields_schema=None,
    )
    assert report["loops"] == loops
    assert report["conditions"] == conditions
