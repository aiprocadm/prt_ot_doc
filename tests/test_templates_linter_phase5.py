"""Phase 5.1 — extended template linter coverage (vNext-DOC-02).

Tests focus on the new behaviors layered on top of the existing balanced-block
checks:
- {% else %} / {% elif … %} directives inside {% if … %}
- Unbalanced delimiter detection ({{/}} and {%/%})
- Optional `available_fields` produces warnings for used-but-undeclared fields
  while ignoring loop-local variables
"""

from __future__ import annotations

from io import BytesIO
from zipfile import ZipFile

import pytest

from app.modules.templates.linter import lint_template, parse_docx_placeholders


def _docx_with_text(text: str) -> bytes:
    bio = BytesIO()
    xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">\n'
        f"  <w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body>\n"
        "</w:document>"
    ).encode("utf-8")
    with ZipFile(bio, "w") as zf:
        zf.writestr("word/document.xml", xml)
    return bio.getvalue()


# ---------- else / elif directives ----------


def test_else_inside_if_block_is_valid() -> None:
    report = lint_template(
        _docx_with_text("{% if person.active %}{{ person.name }}{% else %}Inactive{% endif %}")
    )
    assert report["summary"]["error_count"] == 0


def test_elif_inside_if_block_is_valid() -> None:
    report = lint_template(
        _docx_with_text(
            "{% if person.rank == 1 %}A{% elif person.rank == 2 %}B{% else %}C{% endif %}"
        )
    )
    assert report["summary"]["error_count"] == 0


def test_else_outside_if_is_error() -> None:
    report = lint_template(_docx_with_text("{% else %}orphan{% endif %}"))
    assert any("Unexpected else" in err for err in report["errors"])


def test_elif_outside_if_is_error() -> None:
    report = lint_template(_docx_with_text("{% elif x == 1 %}orphan{% endif %}"))
    assert any("Unexpected elif" in err for err in report["errors"])


def test_elif_with_unsafe_expression_is_error() -> None:
    report = lint_template(_docx_with_text("{% if x %}{% elif y ; danger %}bad{% endif %}"))
    assert any("Unsafe elif expression" in err for err in report["errors"])


# ---------- delimiter balance ----------


def test_unbalanced_double_brace_is_error() -> None:
    report = lint_template(_docx_with_text("Hello {{ name "))
    assert any("Unbalanced placeholder delimiters" in err for err in report["errors"])


def test_unbalanced_block_delim_is_error() -> None:
    report = lint_template(_docx_with_text("{% if x"))
    assert any("Unbalanced block delimiters" in err for err in report["errors"])


def test_balanced_delims_no_error() -> None:
    report = lint_template(_docx_with_text("Hello {{ name }} {% if x %}!{% endif %}"))
    delim_errs = [e for e in report["errors"] if "Unbalanced" in e or "delimiters" in e]
    assert delim_errs == []


# ---------- available_fields warnings ----------


def test_available_fields_not_set_skips_warning() -> None:
    report = lint_template(_docx_with_text("{{ stranger.value }}"))
    assert all("not declared in available_fields" not in w for w in report["warnings"])


def test_available_fields_flags_unknown_root() -> None:
    report = lint_template(
        _docx_with_text("Hello {{ stranger.value }} and {{ person.name }}"),
        available_fields=["person.name", "company.short_name"],
    )
    msgs = [w for w in report["warnings"] if "not declared in available_fields" in w]
    assert any("stranger" in w for w in msgs)
    assert not any("person" in w for w in msgs)


def test_available_fields_accepts_known_root_with_nested_path() -> None:
    report = lint_template(
        _docx_with_text("{{ person.contacts.email }}"),
        available_fields=["person"],
    )
    msgs = [w for w in report["warnings"] if "not declared in available_fields" in w]
    assert msgs == []


def test_available_fields_skips_loop_variable() -> None:
    report = lint_template(
        _docx_with_text("{% for item in items %}{{ item.name }}{% endfor %}"),
        available_fields=["items"],
    )
    msgs = [w for w in report["warnings"] if "not declared in available_fields" in w]
    assert msgs == []


def test_available_fields_flags_unknown_in_condition() -> None:
    report = lint_template(
        _docx_with_text("{% if mystery.flag %}A{% endif %}{{ person.name }}"),
        available_fields=["person"],
    )
    msgs = [w for w in report["warnings"] if "not declared in available_fields" in w]
    assert any("mystery" in w for w in msgs)


def test_available_fields_flags_unknown_in_loop_iter() -> None:
    report = lint_template(
        _docx_with_text("{% for x in unknown_list %}{{ x }}{% endfor %}"),
        available_fields=["person"],
    )
    msgs = [w for w in report["warnings"] if "not declared in available_fields" in w]
    assert any("unknown_list" in w for w in msgs)


# ---------- required_fields still works ----------


def test_required_field_missing_produces_warning() -> None:
    report = lint_template(
        _docx_with_text("Hello {{ first_name }}"),
        required_fields=["first_name", "sign_date"],
    )
    msgs = [w for w in report["warnings"] if "Required field is not used" in w]
    assert any("sign_date" in w for w in msgs)
    assert not any("first_name" in w for w in msgs)


# ---------- delimiters payload exposed by parser ----------


def test_parse_returns_delimiter_counts() -> None:
    parsed = parse_docx_placeholders(_docx_with_text("{{ a }} {{ b }} {% if c %}x{% endif %}"))
    delims = parsed["delimiters"]
    assert delims["placeholder_open"] == 2
    assert delims["placeholder_close"] == 2
    assert delims["block_open"] == 2
    assert delims["block_close"] == 2


# ---------- combined scenarios ----------


@pytest.mark.parametrize(
    "snippet, expected_substring",
    [
        ("{% endif %}orphan", "Unexpected endif"),
        ("{% endfor %}orphan", "Unexpected endfor"),
        ("{% for in items %}{% endfor %}", "Invalid for variable"),
        ("{% if x ; danger %}{% endif %}", "Unsafe if expression"),
    ],
)
def test_legacy_syntactic_errors_still_caught(snippet: str, expected_substring: str) -> None:
    report = lint_template(_docx_with_text(snippet))
    assert any(expected_substring in e for e in report["errors"]), report["errors"]
