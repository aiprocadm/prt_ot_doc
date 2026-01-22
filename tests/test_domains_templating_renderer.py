from __future__ import annotations

from io import BytesIO
from pathlib import Path

from docx import Document

from collections import UserDict

from app.domains.templating.renderer import TemplateRenderer, _coerce_mapping, render_docx


def _build_template(text: str) -> bytes:
    doc = Document()
    doc.add_paragraph(text)
    buffer = BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


def test_coerce_mapping_handles_non_dict() -> None:
    mapping = _coerce_mapping({"a": 1})
    assert mapping == {"a": 1}

    mapping = _coerce_mapping(UserDict({"b": 2}))
    assert mapping == {"b": 2}

    assert _coerce_mapping(None) == {}


def test_render_docx_applies_context(tmp_path: Path) -> None:
    template_bytes = _build_template("Value: {{ value }}")
    rendered = render_docx(template_bytes, {"value": "42"})
    doc = Document(BytesIO(rendered))
    assert "Value: 42" in doc.paragraphs[0].text


def test_template_renderer_writes_to_path(tmp_path: Path) -> None:
    template_path = tmp_path / "template.docx"
    template_path.write_bytes(_build_template("Hello {{ name }}"))
    renderer = TemplateRenderer(template_path=str(template_path))
    output_path = tmp_path / "out.docx"
    result_path = Path(renderer.render({"name": "Bob"}, str(output_path)))
    assert result_path == output_path
    assert output_path.exists()
    doc = Document(output_path)
    assert doc.paragraphs[0].text == "Hello Bob"
