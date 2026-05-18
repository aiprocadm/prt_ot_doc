"""Tests for the template variable inspector (Phase 5.1 / vNext-DOC-02).

`inspect_template_context` cross-checks a DOCX template against an
available-variables schema. It is the data behind the IDE-style "what
variables can I use" panel that admins see when uploading templates.
"""

from __future__ import annotations

import zipfile
from io import BytesIO

from app.modules.templates import inspect_docx_template
from app.modules.templates.linter import inspect_template_context


def _docx_with_text(text: str) -> bytes:
    bio = BytesIO()
    xml = (
        "<?xml version='1.0' encoding='UTF-8' standalone='yes'?>"
        "<w:document xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'>"
        f"<w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body>"
        "</w:document>"
    )
    with zipfile.ZipFile(bio, "w") as zf:
        zf.writestr("word/document.xml", xml)
    return bio.getvalue()


# -----------------------------------------------------------------------------
# Basic shape & defaults
# -----------------------------------------------------------------------------


def test_empty_inputs_return_empty_report() -> None:
    report = inspect_template_context(_docx_with_text("plain text"), available_variables={})
    assert report["available"] == []
    assert report["used"] == []
    assert report["undefined"] == []
    assert report["unused"] == []
    assert report["required_missing"] == []
    assert report["summary"]["available_count"] == 0


def test_available_variables_are_flattened_to_dotted_paths() -> None:
    schema = {"employee": {"name": "", "position": {"title": ""}}}
    report = inspect_template_context(_docx_with_text(""), available_variables=schema)
    assert set(report["available"]) >= {
        "employee",
        "employee.name",
        "employee.position",
        "employee.position.title",
    }


def test_used_paths_are_extracted_from_template() -> None:
    report = inspect_template_context(
        _docx_with_text("{{ employee.name }} {{ company.title }}"),
        available_variables={"employee": {"name": ""}, "company": {"title": ""}},
    )
    assert "employee.name" in report["used"]
    assert "company.title" in report["used"]


# -----------------------------------------------------------------------------
# Undefined / unused detection
# -----------------------------------------------------------------------------


def test_undefined_when_root_missing_entirely() -> None:
    report = inspect_template_context(
        _docx_with_text("{{ contractor.legal_name }}"),
        available_variables={"employee": {"name": ""}},
    )
    assert "contractor.legal_name" in report["undefined"]


def test_undefined_when_root_present_but_nested_missing() -> None:
    report = inspect_template_context(
        _docx_with_text("{{ employee.salary }}"),
        available_variables={"employee": {"name": ""}},
    )
    assert "employee.salary" in report["undefined"]


def test_not_undefined_when_path_matches() -> None:
    report = inspect_template_context(
        _docx_with_text("{{ employee.name }}"),
        available_variables={"employee": {"name": ""}},
    )
    assert report["undefined"] == []


def test_unused_when_schema_has_extra_paths() -> None:
    report = inspect_template_context(
        _docx_with_text("{{ employee.name }}"),
        available_variables={"employee": {"name": ""}, "company": {"title": ""}},
    )
    assert any(path.startswith("company") for path in report["unused"])


# -----------------------------------------------------------------------------
# Required fields
# -----------------------------------------------------------------------------


def test_required_missing_when_field_not_in_template() -> None:
    report = inspect_template_context(
        _docx_with_text("{{ employee.name }}"),
        available_variables={"employee": {"name": "", "position": ""}},
        required_fields=["employee.name", "employee.position"],
    )
    assert "employee.position" in report["required_missing"]


def test_required_missing_empty_when_all_used() -> None:
    report = inspect_template_context(
        _docx_with_text("{{ employee.name }} {{ employee.position }}"),
        available_variables={"employee": {"name": "", "position": ""}},
        required_fields=["employee.name", "employee.position"],
    )
    assert report["required_missing"] == []


# -----------------------------------------------------------------------------
# Loops / filters
# -----------------------------------------------------------------------------


def test_loop_variable_not_flagged_as_undefined() -> None:
    report = inspect_template_context(
        _docx_with_text("{% for emp in employees %}{{ emp.name }}{% endfor %}"),
        available_variables={"employees": []},
    )
    assert "emp.name" not in report["undefined"]


def test_loops_and_conditions_surfaced() -> None:
    report = inspect_template_context(
        _docx_with_text(
            "{% if active %}{% for x in items %}{{ x }}{% endfor %}{% endif %}"
        ),
        available_variables={"active": False, "items": []},
    )
    assert len(report["loops"]) == 1
    assert len(report["conditions"]) == 1
    assert report["loops"][0]["var"] == "x"


def test_unknown_filter_listed() -> None:
    report = inspect_template_context(
        _docx_with_text("{{ name | nonexistent_filter }}"),
        available_variables={"name": ""},
    )
    assert "nonexistent_filter" in report["unknown_filters"]


def test_known_filter_not_flagged() -> None:
    report = inspect_template_context(
        _docx_with_text("{{ name | upper }}"),
        available_variables={"name": ""},
    )
    assert report["unknown_filters"] == []


# -----------------------------------------------------------------------------
# Service-level wiring
# -----------------------------------------------------------------------------


def test_service_facade_returns_same_shape_as_linter() -> None:
    docx = _docx_with_text("{{ employee.name }}")
    direct = inspect_template_context(docx, available_variables={"employee": {"name": ""}})
    via_service = inspect_docx_template(docx, available_variables={"employee": {"name": ""}})
    assert direct == via_service


def test_summary_counts_match_lists() -> None:
    report = inspect_template_context(
        _docx_with_text("{{ a.b }} {{ c.d }}"),
        available_variables={"a": {"b": ""}, "extra": {"k": ""}},
        required_fields=["a.b", "c.d", "missing.x"],
    )
    summary = report["summary"]
    assert summary["available_count"] == len(report["available"])
    assert summary["used_count"] == len(report["used"])
    assert summary["undefined_count"] == len(report["undefined"])
    assert summary["unused_count"] == len(report["unused"])
    assert summary["required_missing_count"] == len(report["required_missing"])
    assert summary["unknown_filter_count"] == len(report["unknown_filters"])
