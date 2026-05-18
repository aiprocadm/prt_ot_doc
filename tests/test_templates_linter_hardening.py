"""Hardening tests for the DOCX template linter (Phase 5.1 / vNext-DOC-02).

Covers edge cases beyond the original balanced-blocks check:
- empty placeholders, duplicate placeholders, unknown filters,
- undefined variables vs. a sample schema,
- unused variables (provided but never referenced),
- malformed loops, malformed conditions, nested blocks,
- whitespace and structural quirks.
"""

from __future__ import annotations

import zipfile
from io import BytesIO

import pytest

from app.modules.templates.linter import lint_template


def _docx_with_text(text: str, *, header: str | None = None, footer: str | None = None) -> bytes:
    bio = BytesIO()

    def _wrap(body: str) -> str:
        return (
            "<?xml version='1.0' encoding='UTF-8' standalone='yes'?>"
            "<w:document xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'>"
            f"<w:body><w:p><w:r><w:t>{body}</w:t></w:r></w:p></w:body>"
            "</w:document>"
        )

    with zipfile.ZipFile(bio, "w") as zf:
        zf.writestr("word/document.xml", _wrap(text))
        if header is not None:
            zf.writestr("word/header1.xml", _wrap(header))
        if footer is not None:
            zf.writestr("word/footer1.xml", _wrap(footer))
    return bio.getvalue()


# -----------------------------------------------------------------------------
# 1. Empty placeholders
# -----------------------------------------------------------------------------


def test_empty_placeholder_is_an_error() -> None:
    report = lint_template(_docx_with_text("{{ }}"))
    assert report["summary"]["empty_placeholder_count"] == 1
    assert any("Empty placeholder" in err for err in report["errors"])


def test_empty_placeholder_alongside_valid_one() -> None:
    report = lint_template(_docx_with_text("{{ }} {{ employee.name }}"))
    assert report["summary"]["empty_placeholder_count"] == 1
    assert "employee.name" in report["found_fields"]


# -----------------------------------------------------------------------------
# 2. Duplicate placeholders
# -----------------------------------------------------------------------------


def test_duplicate_placeholder_under_threshold_is_silent() -> None:
    report = lint_template(_docx_with_text("{{ a }} {{ a }}"))
    # 2 occurrences — kept silent; threshold is "consider a loop" at >=3.
    assert all("consider a loop" not in w for w in report["warnings"])


def test_duplicate_placeholder_warns_at_threshold() -> None:
    report = lint_template(_docx_with_text("{{ a }} {{ a }} {{ a }}"))
    assert report["summary"]["duplicate_count"] >= 1
    assert any("consider a loop" in w for w in report["warnings"])


# -----------------------------------------------------------------------------
# 3. Unknown filter detection
# -----------------------------------------------------------------------------


def test_known_filter_is_silent() -> None:
    report = lint_template(_docx_with_text("{{ name | upper }}"))
    assert all("Unknown filter" not in w for w in report["warnings"])
    assert any(item["name"] == "upper" for item in report["filters"])


def test_unknown_filter_emits_warning() -> None:
    report = lint_template(_docx_with_text("{{ name | upperr }}"))
    assert any("Unknown filter" in w and "upperr" in w for w in report["warnings"])


def test_custom_filter_can_be_whitelisted() -> None:
    report = lint_template(
        _docx_with_text("{{ name | rubles }}"),
        known_filters={"rubles"},
    )
    assert all("Unknown filter" not in w for w in report["warnings"])


# -----------------------------------------------------------------------------
# 4. Undefined / unused variables vs. sample schema
# -----------------------------------------------------------------------------


def test_undefined_variable_is_warning_when_schema_supplied() -> None:
    schema = {"employee": {"name": ""}}
    report = lint_template(
        _docx_with_text("{{ employee.name }} {{ company.title }}"),
        sample_schema=schema,
    )
    assert "company.title" in report["undefined_variables"]
    assert any("Undefined variable" in w and "company.title" in w for w in report["warnings"])


def test_no_undefined_warnings_when_schema_matches() -> None:
    schema = {"employee": {"name": "", "position": ""}}
    report = lint_template(
        _docx_with_text("{{ employee.name }} {{ employee.position }}"),
        sample_schema=schema,
    )
    assert report["undefined_variables"] == []
    assert all("Undefined variable" not in w for w in report["warnings"])


def test_unused_variable_listed_when_schema_richer_than_template() -> None:
    schema = {"employee": {"name": ""}, "extra": {"unused": ""}}
    report = lint_template(
        _docx_with_text("{{ employee.name }}"),
        sample_schema=schema,
    )
    assert "extra.unused" in report["unused_variables"] or "extra" in report["unused_variables"]


def test_loop_variable_is_not_undefined() -> None:
    schema = {"employees": []}
    report = lint_template(
        _docx_with_text("{% for emp in employees %}{{ emp.name }}{% endfor %}"),
        sample_schema=schema,
    )
    # 'emp.name' uses loop variable 'emp', not a top-level schema key —
    # it must NOT show up as undefined.
    assert "emp.name" not in report["undefined_variables"]


# -----------------------------------------------------------------------------
# 5. Malformed loops / conditions
# -----------------------------------------------------------------------------


def test_invalid_for_variable_is_error() -> None:
    report = lint_template(_docx_with_text("{% for 1bad in items %}{{ 1bad }}{% endfor %}"))
    assert any("Invalid for variable" in err for err in report["errors"])


def test_unsafe_if_expression_is_error() -> None:
    report = lint_template(_docx_with_text("{% if __import__('os') %}{% endif %}"))
    assert any("Unsafe if expression" in err for err in report["errors"])


def test_unsafe_for_iterable_is_error() -> None:
    report = lint_template(_docx_with_text("{% for x in __import__('os').listdir %}{% endfor %}"))
    assert any("Unsafe for iterable" in err for err in report["errors"])


def test_unknown_directive_is_error() -> None:
    report = lint_template(_docx_with_text("{% while True %}{% endwhile %}"))
    assert any("Unknown directive" in err for err in report["errors"])


def test_unclosed_if_is_error() -> None:
    report = lint_template(_docx_with_text("{% if a %}{{ a }}"))
    assert any("Unclosed blocks" in err for err in report["errors"])


def test_unexpected_endif_is_error() -> None:
    report = lint_template(_docx_with_text("{{ a }}{% endif %}"))
    assert "Unexpected endif" in report["errors"]


def test_unexpected_endfor_is_error() -> None:
    report = lint_template(_docx_with_text("{{ a }}{% endfor %}"))
    assert "Unexpected endfor" in report["errors"]


# -----------------------------------------------------------------------------
# 6. Nested blocks
# -----------------------------------------------------------------------------


def test_nested_if_for_balanced() -> None:
    report = lint_template(
        _docx_with_text(
            "{% if user.active %}"
            "{% for item in user.items %}{{ item.name }}{% endfor %}"
            "{% endif %}"
        )
    )
    assert report["summary"]["error_count"] == 0
    assert report["summary"]["loop_count"] == 1
    assert report["summary"]["condition_count"] == 1


def test_nested_blocks_with_mismatched_close_is_error() -> None:
    report = lint_template(
        _docx_with_text(
            "{% if a %}{% for x in xs %}{{ x }}{% endif %}{% endfor %}"
        )
    )
    # The endif comes while still inside the for -> Unexpected endif,
    # and then endfor at outer level is also unexpected.
    assert any("Unexpected endif" in err for err in report["errors"])


# -----------------------------------------------------------------------------
# 7. Required fields
# -----------------------------------------------------------------------------


def test_required_field_warning_when_missing() -> None:
    report = lint_template(
        _docx_with_text("{{ employee.name }}"),
        required_fields=["employee.name", "employee.position"],
    )
    assert any("employee.position" in w for w in report["warnings"])


def test_required_field_silent_when_present() -> None:
    report = lint_template(
        _docx_with_text("{{ employee.name }} {{ employee.position }}"),
        required_fields=["employee.name", "employee.position"],
    )
    assert all("Required field" not in w for w in report["warnings"])


# -----------------------------------------------------------------------------
# 8. Header / Footer scanning
# -----------------------------------------------------------------------------


def test_placeholders_in_header_are_scanned() -> None:
    report = lint_template(_docx_with_text("body", header="{{ header.title }}"))
    assert "header.title" in report["found_fields"]


def test_placeholders_in_footer_are_scanned() -> None:
    report = lint_template(_docx_with_text("body", footer="{{ footer.page }}"))
    assert "footer.page" in report["found_fields"]


def test_header_unknown_filter_warning() -> None:
    report = lint_template(_docx_with_text("body", header="{{ x | notafilter }}"))
    assert any("Unknown filter" in w and "notafilter" in w for w in report["warnings"])


# -----------------------------------------------------------------------------
# 9. Backwards compatibility — existing callers
# -----------------------------------------------------------------------------


def test_backward_compat_placeholders_alias_kept() -> None:
    report = lint_template(_docx_with_text("{{ a }}"))
    assert report["placeholders"] == report["found_fields"]


def test_backward_compat_field_paths_includes_conditions() -> None:
    report = lint_template(_docx_with_text("{% if user.active %}x{% endif %}"))
    assert "user.active" in report["field_paths"]


def test_summary_counts_match_lists() -> None:
    report = lint_template(
        _docx_with_text("{{ a }} {{ b }} {% if c %}{{ d }}{% endif %}"),
    )
    assert report["summary"]["field_count"] == len(report["found_fields"])
    assert report["summary"]["condition_count"] == len(report["blocks"]["conditions"])
    assert report["summary"]["filter_count"] == len(report["filters"])


# -----------------------------------------------------------------------------
# 10. Edge cases
# -----------------------------------------------------------------------------


def test_filter_with_default_argument_is_recognised() -> None:
    report = lint_template(_docx_with_text("{{ name | default('—') }}"))
    assert any(item["name"] == "default" for item in report["filters"])


def test_multiple_filters_chain_all_listed() -> None:
    report = lint_template(_docx_with_text("{{ name | upper | trim }}"))
    used = {item["name"] for item in report["filters"]}
    assert {"upper", "trim"} <= used


def test_safe_expression_with_dotted_path_and_index() -> None:
    report = lint_template(_docx_with_text("{% if items[0].name %}x{% endif %}"))
    assert all("Unsafe" not in err for err in report["errors"])


@pytest.mark.parametrize(
    "snippet,should_error",
    [
        ("", False),  # no placeholders, no errors
        ("plain text only", False),
        ("{{ a.b.c }}", False),
        ("{{ a }} {{ b }} {{ c }} {{ d }} {{ e }}", False),
        ("{% if a %}", True),  # unclosed
        ("{% endif %}", True),
        ("{% endfor %}", True),
    ],
)
def test_param_lint_table(snippet: str, should_error: bool) -> None:
    report = lint_template(_docx_with_text(snippet))
    has_error = report["summary"]["error_count"] > 0
    assert has_error is should_error
