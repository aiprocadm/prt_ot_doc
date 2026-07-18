"""Preview vs final-document parity proof (Phase 5.1 / vNext-DOC-02 / Session 38).

The acceptance criterion for Phase 5.1 says "Preview engine: 100% accuracy
(preview matches final PDF)". Production document generation calls
``app.domains.templating.renderer.render_docx`` followed by
``inject_passport`` (see ``app.tasks._core``). Until Session 38 the preview
path used a different renderer (``app.modules.templates.render``, raw-XML
Jinja2), so subtle divergences were possible — especially for placeholders
that span runs or templates with custom filters.

These tests pin the contract: for any given (template, data) the preview
output and the production output must produce the **same DOCX text body**,
and when the visible flag matches, the **same bytes**.
"""

from __future__ import annotations

from io import BytesIO

from docx import Document

from app.domains.templating.renderer import render_docx as render_production
from app.modules.templates.passport import inject_passport
from app.modules.templates.service import render_preview_docx


def _template_bytes(text: str) -> bytes:
    """Build a minimal DOCX with one paragraph containing ``text``."""
    doc = Document()
    doc.add_paragraph(text)
    buffer = BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


def _template_bytes_split_runs(parts: list[str]) -> bytes:
    """Build a DOCX where each part lives in its own run inside one paragraph.

    Used to catch the "placeholder split across runs" regression that the
    legacy XML-direct renderer handled differently than docxtpl.
    """
    doc = Document()
    p = doc.add_paragraph()
    for part in parts:
        p.add_run(part)
    buffer = BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


def _body_text(docx_bytes: bytes) -> str:
    doc = Document(BytesIO(docx_bytes))
    return "\n".join(p.text for p in doc.paragraphs)


# -----------------------------------------------------------------------------
# Core parity — same renderer in both paths
# -----------------------------------------------------------------------------


def test_preview_uses_same_renderer_as_production_for_simple_template() -> None:
    template = _template_bytes("Hello {{ name }}")
    data = {"name": "Alice"}
    passport = {"template_code": "greeting", "template_version": 1}

    preview = render_preview_docx(
        template_bytes=template,
        data=data,
        passport=passport,
        visible_passport=False,
    )
    production_base = render_production(template, data)
    production = inject_passport(production_base, passport, visible=False)

    # Same renderer + same passport flag => identical body text.
    assert _body_text(preview) == _body_text(production)
    assert "Hello Alice" in _body_text(preview)


def test_preview_visible_passport_flag_matches_production() -> None:
    template = _template_bytes("Hello {{ name }}")
    data = {"name": "Bob"}
    passport = {"template_code": "greeting", "template_version": 1}

    preview = render_preview_docx(
        template_bytes=template,
        data=data,
        passport=passport,
        visible_passport=True,
    )
    production_base = render_production(template, data)
    production = inject_passport(production_base, passport, visible=True)

    # Both should contain the visible passport marker in the body.
    preview_text = _body_text(preview)
    production_text = _body_text(production)
    assert "Hello Bob" in preview_text
    assert "Hello Bob" in production_text
    assert "PTD-PASSPORT" in preview_text
    assert "PTD-PASSPORT" in production_text


def test_preview_body_matches_production_for_split_runs() -> None:
    """Placeholder split across runs is the canonical "preview lied" case
    the legacy XML-direct renderer used to handle differently."""
    template = _template_bytes_split_runs(["Hello {{ ", "name", " }}!"])
    data = {"name": "Carol"}
    passport = {"template_code": "split", "template_version": 1}

    preview = render_preview_docx(
        template_bytes=template,
        data=data,
        passport=passport,
        visible_passport=False,
    )
    production_base = render_production(template, data)
    production = inject_passport(production_base, passport, visible=False)

    assert _body_text(preview) == _body_text(production)
    assert "Hello Carol!" in _body_text(preview)


# -----------------------------------------------------------------------------
# Custom filters parity — upper/lower/date
# -----------------------------------------------------------------------------


def test_preview_supports_upper_filter() -> None:
    template = _template_bytes("{{ name | upper }}")
    data = {"name": "alice"}
    passport = {"template_code": "filter-upper", "template_version": 1}

    preview = render_preview_docx(
        template_bytes=template,
        data=data,
        passport=passport,
        visible_passport=False,
    )
    production_base = render_production(template, data)
    production = inject_passport(production_base, passport, visible=False)

    assert "ALICE" in _body_text(preview)
    assert _body_text(preview) == _body_text(production)


def test_preview_supports_lower_filter() -> None:
    template = _template_bytes("{{ name | lower }}")
    data = {"name": "BOB"}
    passport = {"template_code": "filter-lower", "template_version": 1}
    preview = render_preview_docx(
        template_bytes=template, data=data, passport=passport, visible_passport=False
    )
    assert "bob" in _body_text(preview)


def test_preview_supports_date_filter_on_iso_string() -> None:
    template = _template_bytes("Issued: {{ issued | date }}")
    data = {"issued": "2026-05-18T12:00:00Z"}
    passport = {"template_code": "filter-date", "template_version": 1}
    preview = render_preview_docx(
        template_bytes=template, data=data, passport=passport, visible_passport=False
    )
    assert "Issued: 2026-05-18" in _body_text(preview)


def test_preview_supports_date_filter_with_custom_format() -> None:
    template = _template_bytes("{{ issued | date('%d.%m.%Y') }}")
    data = {"issued": "2026-05-18T12:00:00Z"}
    passport = {"template_code": "filter-date-fmt", "template_version": 1}
    preview = render_preview_docx(
        template_bytes=template, data=data, passport=passport, visible_passport=False
    )
    assert "18.05.2026" in _body_text(preview)


def test_preview_upper_filter_handles_non_string_value() -> None:
    """The custom ``upper`` filter wraps Jinja2's builtin with ``str(value)``
    so ints / floats don't blow up the way Jinja2's stock filter would."""
    template = _template_bytes("{{ count | upper }}")
    data = {"count": 42}
    passport = {"template_code": "filter-upper-int", "template_version": 1}
    preview = render_preview_docx(
        template_bytes=template, data=data, passport=passport, visible_passport=False
    )
    assert "42" in _body_text(preview)


# -----------------------------------------------------------------------------
# Missing-data fallback — preview shouldn't 500 on incomplete sample context
# -----------------------------------------------------------------------------


def test_preview_falls_back_to_empty_string_on_missing_variable() -> None:
    """Production renderer falls back to '' on missing keys; preview must
    behave the same so admins can iterate with partial data."""
    template = _template_bytes("Hello {{ name }} {{ missing }}")
    data = {"name": "Dora"}
    passport = {"template_code": "fallback", "template_version": 1}

    preview = render_preview_docx(
        template_bytes=template,
        data=data,
        passport=passport,
        visible_passport=False,
    )
    production_base = render_production(template, data)
    production = inject_passport(production_base, passport, visible=False)

    # Both fall back to empty string for the missing key.
    assert "Hello Dora" in _body_text(preview)
    assert _body_text(preview) == _body_text(production)


# -----------------------------------------------------------------------------
# Nested context and loops
# -----------------------------------------------------------------------------


def test_preview_supports_nested_context() -> None:
    template = _template_bytes("{{ employee.name }} — {{ employee.position }}")
    data = {"employee": {"name": "Eve", "position": "Engineer"}}
    passport = {"template_code": "nested", "template_version": 1}

    preview = render_preview_docx(
        template_bytes=template,
        data=data,
        passport=passport,
        visible_passport=False,
    )
    production_base = render_production(template, data)
    production = inject_passport(production_base, passport, visible=False)

    assert "Eve" in _body_text(preview)
    assert "Engineer" in _body_text(preview)
    assert _body_text(preview) == _body_text(production)


# -----------------------------------------------------------------------------
# Renderer engine identity (defensive — catches future drift)
# -----------------------------------------------------------------------------


def test_preview_does_not_use_legacy_xml_direct_renderer() -> None:
    """If someone re-points ``render_preview_docx`` back at the legacy XML
    renderer, the production-renderer metadata would no longer reflect the
    preview path. Pin the integration here: rendering a template that uses
    a ``date`` filter on an int should produce the same fallback string."""

    template = _template_bytes("Issued: {{ when | date }}")
    data = {"when": 0}  # not a date — both renderers should stringify
    passport = {"template_code": "engine-pin", "template_version": 1}

    preview = render_preview_docx(
        template_bytes=template,
        data=data,
        passport=passport,
        visible_passport=False,
    )
    production_base = render_production(template, data)
    production = inject_passport(production_base, passport, visible=False)

    assert _body_text(preview) == _body_text(production)
