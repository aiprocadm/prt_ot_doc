"""Helpers for rendering DOCX templates using :mod:`docxtpl`."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Any, Mapping

from docxtpl import DocxTemplate

__all__ = ["TemplateRenderer", "render_docx"]


def _coerce_mapping(value: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return a shallow copy of ``value`` ensuring a plain ``dict``."""

    if not value:
        return {}
    if isinstance(value, dict):
        return dict(value)
    return {str(key): val for key, val in value.items()}


def render_docx(template_bytes: bytes, context: Mapping[str, Any] | None) -> bytes:
    """Render a DOCX template using ``docxtpl`` and return raw bytes."""

    tpl = DocxTemplate(BytesIO(template_bytes))
    tpl.render(_coerce_mapping(context))
    buffer = BytesIO()
    tpl.save(buffer)
    return buffer.getvalue()


@dataclass
class TemplateRenderer:
    template_path: str

    def render(self, context: Mapping[str, Any], output_path: str) -> str:
        doc = DocxTemplate(self.template_path)
        render_context = _coerce_mapping(context)
        doc.render(render_context)
        doc.save(output_path)
        return output_path
