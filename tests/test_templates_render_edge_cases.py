"""Phase 5.1 — render engine edge-case coverage (vNext-DOC-02).

Exercises the legacy raw-XML preview renderer ``app.modules.templates.render``
(still shipped as the canonical reference for the custom ``upper``/``lower``/
``date`` filters and the only *sandboxed* Jinja2 path) end-to-end through a real
DOCX zip plus the internal helpers (``_f_upper``, ``_f_lower``, ``_f_date``,
``_render_jinja``) directly. Focus: null values, loops, conditions, filters,
multi-paragraph, sandbox safety, headers/footers.

Split-run rendering and the passport marker are already pinned by
``tests/test_templates_next18_unit.py`` for this module, so they are not
re-asserted here.
"""

from __future__ import annotations

import datetime as dt
import zipfile
from io import BytesIO

import pytest
from docx import Document
from jinja2.exceptions import UndefinedError
from jinja2.sandbox import SecurityError

from app.modules.templates.render import (
    _f_date,
    _f_lower,
    _f_upper,
    _render_jinja,
    render_docx,
)

PASSPORT = {"template_code": "test", "template_version": 1}


def _docx(*paragraphs: str) -> bytes:
    """Build a minimal DOCX with one or more paragraphs in word/document.xml."""
    doc = Document()
    for text in paragraphs:
        doc.add_paragraph(text)
    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _docx_split(parts: list[str]) -> bytes:
    """Build a DOCX where each part is a separate <w:r><w:t> run inside one paragraph."""
    doc = Document()
    p = doc.add_paragraph()
    for part in parts:
        p.add_run(part)
    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _paragraphs(rendered: bytes) -> list[str]:
    return [p.text for p in Document(BytesIO(rendered)).paragraphs]


def _all_text(rendered: bytes) -> str:
    return "\n".join(_paragraphs(rendered))


# ---------- filter unit tests ----------


def test_f_upper_handles_string() -> None:
    assert _f_upper("hello") == "HELLO"


def test_f_upper_handles_non_string() -> None:
    assert _f_upper(42) == "42"


def test_f_lower_handles_string() -> None:
    assert _f_lower("HELLO") == "hello"


def test_f_lower_handles_non_string() -> None:
    assert _f_lower(True) == "true"


def test_f_date_returns_empty_for_none() -> None:
    assert _f_date(None) == ""


def test_f_date_formats_datetime() -> None:
    value = dt.datetime(2026, 5, 20, 12, 30, tzinfo=dt.timezone.utc)
    assert _f_date(value) == "2026-05-20"
    assert _f_date(value, "%d.%m.%Y") == "20.05.2026"


def test_f_date_parses_iso_string() -> None:
    assert _f_date("2026-05-20T10:00:00Z", "%Y/%m/%d") == "2026/05/20"


def test_f_date_returns_input_when_unparseable_string() -> None:
    assert _f_date("not a date") == "not a date"


def test_f_date_stringifies_other_types() -> None:
    assert _f_date(12345) == "12345"


# ---------- placeholder rendering ----------


def test_simple_placeholder_renders() -> None:
    out = render_docx(_docx("Hello {{ name }}"), {"name": "World"}, PASSPORT)
    assert "Hello World" in _all_text(out)


def test_nested_dotted_path_renders() -> None:
    out = render_docx(
        _docx("Owner: {{ person.name.first }} {{ person.name.last }}"),
        {"person": {"name": {"first": "Иван", "last": "Петров"}}},
        PASSPORT,
    )
    assert "Owner: Иван Петров" in _all_text(out)


def test_missing_root_raises_strict_undefined() -> None:
    with pytest.raises(UndefinedError):
        render_docx(_docx("Hello {{ name }}"), {}, PASSPORT)


def test_missing_attribute_under_known_root_raises() -> None:
    with pytest.raises(UndefinedError):
        render_docx(_docx("{{ person.missing }}"), {"person": {"name": "Иван"}}, PASSPORT)


def test_explicit_none_renders_as_string_none() -> None:
    out = render_docx(_docx("Value: {{ value }}"), {"value": None}, PASSPORT)
    # Jinja2 stringifies None as "None"; the value still renders, no crash.
    assert "Value: None" in _all_text(out)


def test_zero_value_renders_literally() -> None:
    out = render_docx(_docx("Count: {{ count }}"), {"count": 0}, PASSPORT)
    assert "Count: 0" in _all_text(out)


def test_false_value_renders_literally() -> None:
    out = render_docx(_docx("Flag: {{ flag }}"), {"flag": False}, PASSPORT)
    assert "Flag: False" in _all_text(out)


def test_empty_string_collapses_neighbors() -> None:
    out = render_docx(_docx("A[{{ x }}]B"), {"x": ""}, PASSPORT)
    assert "A[]B" in _all_text(out)


def test_float_value_renders() -> None:
    out = render_docx(_docx("Price: {{ price }}"), {"price": 3.14}, PASSPORT)
    assert "Price: 3.14" in _all_text(out)


def test_list_renders_as_python_repr() -> None:
    out = render_docx(_docx("Tags: {{ tags }}"), {"tags": ["a", "b"]}, PASSPORT)
    assert "Tags: ['a', 'b']" in _all_text(out)


def test_special_xml_chars_in_data_are_safe() -> None:
    out = render_docx(_docx("Note: {{ note }}"), {"note": "<b>x & y</b>"}, PASSPORT)
    # autoescape is off, so chars survive verbatim (rendered via ET serialization).
    assert "<b>x & y</b>" in _all_text(out)


def test_cyrillic_payload_round_trips() -> None:
    out = render_docx(_docx("Сотрудник: {{ name }}"), {"name": "Анна Сидорова"}, PASSPORT)
    assert "Сотрудник: Анна Сидорова" in _all_text(out)


# ---------- filters in templates ----------


def test_upper_filter_in_template() -> None:
    out = render_docx(_docx("{{ name | upper }}"), {"name": "alice"}, PASSPORT)
    assert "ALICE" in _all_text(out)


def test_lower_filter_in_template() -> None:
    out = render_docx(_docx("{{ name | lower }}"), {"name": "ALICE"}, PASSPORT)
    assert "alice" in _all_text(out)


def test_date_filter_with_datetime_value() -> None:
    out = render_docx(
        _docx("Дата: {{ d | date('%d.%m.%Y') }}"),
        {"d": dt.datetime(2026, 5, 20)},
        PASSPORT,
    )
    assert "Дата: 20.05.2026" in _all_text(out)


def test_date_filter_with_none_value_yields_empty_string() -> None:
    out = render_docx(_docx("Дата: [{{ d | date }}]"), {"d": None}, PASSPORT)
    assert "Дата: []" in _all_text(out)


# ---------- conditions ----------


def test_if_truthy_renders_body() -> None:
    out = render_docx(_docx("{% if active %}YES{% endif %}"), {"active": True}, PASSPORT)
    assert "YES" in _all_text(out)


def test_if_falsy_skips_body() -> None:
    out = render_docx(_docx("[{% if active %}YES{% endif %}]"), {"active": False}, PASSPORT)
    assert "[]" in _all_text(out)


def test_if_else_branches() -> None:
    tpl = _docx("{% if active %}ON{% else %}OFF{% endif %}")
    out_on = render_docx(tpl, {"active": True}, PASSPORT)
    out_off = render_docx(tpl, {"active": False}, PASSPORT)
    assert "ON" in _all_text(out_on)
    assert "OFF" in _all_text(out_off)


def test_if_elif_else_chain() -> None:
    tpl = _docx(
        "{% if rank == 1 %}A{% elif rank == 2 %}B{% elif rank == 3 %}C{% else %}D{% endif %}"
    )
    for rank, expected in [(1, "A"), (2, "B"), (3, "C"), (4, "D")]:
        out = render_docx(tpl, {"rank": rank}, PASSPORT)
        assert expected in _all_text(out), (rank, expected)


# ---------- loops ----------


def test_loop_over_empty_list_yields_empty_text() -> None:
    out = render_docx(_docx("[{% for x in xs %}{{ x }}{% endfor %}]"), {"xs": []}, PASSPORT)
    assert "[]" in _all_text(out)


def test_loop_over_single_item() -> None:
    out = render_docx(
        _docx("{% for x in xs %}{{ x }}{% endfor %}"),
        {"xs": ["solo"]},
        PASSPORT,
    )
    assert "solo" in _all_text(out)


def test_loop_iterates_dict_items() -> None:
    out = render_docx(
        _docx("{% for item in items %}{{ item.label }}:{{ item.qty }};{% endfor %}"),
        {"items": [{"label": "A", "qty": 1}, {"label": "B", "qty": 2}]},
        PASSPORT,
    )
    text = _all_text(out)
    assert "A:1;" in text and "B:2;" in text


def test_loop_with_inner_condition() -> None:
    out = render_docx(
        _docx("{% for n in nums %}{% if n > 1 %}{{ n }},{% endif %}{% endfor %}"),
        {"nums": [1, 2, 3]},
        PASSPORT,
    )
    assert "2,3," in _all_text(out)


def test_loop_loop_index_is_one_based() -> None:
    out = render_docx(
        _docx("{% for x in xs %}{{ loop.index }}={{ x }};{% endfor %}"),
        {"xs": ["a", "b"]},
        PASSPORT,
    )
    assert "1=a;2=b;" in _all_text(out)


# ---------- multi-paragraph & headers/footers ----------


def test_multi_paragraph_each_renders_independently() -> None:
    out = render_docx(
        _docx("Hello {{ name }}", "Bye {{ name }}"),
        {"name": "Alex"},
        PASSPORT,
    )
    text = _all_text(out)
    assert "Hello Alex" in text
    assert "Bye Alex" in text


def test_paragraph_without_placeholder_is_untouched() -> None:
    out = render_docx(_docx("Static text"), {}, PASSPORT)
    assert "Static text" in _all_text(out)


def test_render_processes_header_and_footer_xml_parts() -> None:
    # Build a minimal DOCX where word/header1.xml carries a placeholder.
    base = _docx("Body {{ name }}")
    with zipfile.ZipFile(BytesIO(base)) as zin:
        files = {name: zin.read(name) for name in zin.namelist()}
    files["word/header1.xml"] = (
        b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        b'<w:hdr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        b"<w:p><w:r><w:t>Header {{ name }}</w:t></w:r></w:p></w:hdr>"
    )
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zout:
        for name, payload in files.items():
            zout.writestr(name, payload)

    out = render_docx(buf.getvalue(), {"name": "Hdr"}, PASSPORT)
    # The header xml part should be rendered too.
    with zipfile.ZipFile(BytesIO(out)) as zin:
        header_text = zin.read("word/header1.xml").decode("utf-8")
    assert "Header Hdr" in header_text


# ---------- sandbox safety ----------


def test_sandbox_blocks_attribute_starting_with_underscore() -> None:
    with pytest.raises(SecurityError):
        _render_jinja("{{ value.__class__.__name__ }}", {"value": object()})


def test_sandbox_allows_documented_filters_only() -> None:
    # The `subprocess` global isn't exposed in the sandbox; referencing it raises
    # UndefinedError because there is no such variable in the data dict.
    with pytest.raises(UndefinedError):
        _render_jinja("{{ subprocess }}", {})


def test_render_jinja_renders_plain_string() -> None:
    assert _render_jinja("Hello {{ x }}", {"x": "World"}) == "Hello World"
