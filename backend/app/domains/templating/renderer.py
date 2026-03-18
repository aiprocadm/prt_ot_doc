"""Helpers for rendering DOCX templates using :mod:`docxtpl`."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any, Mapping

from docxtpl import DocxTemplate
from jinja2 import Environment, StrictUndefined, UndefinedError

__all__ = ["RenderedTemplate", "TemplateRenderer", "render_docx", "render_docx_with_metadata"]



def _coerce_mapping(value: Mapping[str, Any] | None) -> dict[str, Any]:
    if not value:
        return {}
    if isinstance(value, dict):
        return dict(value)
    return {str(key): val for key, val in value.items()}


@dataclass(frozen=True)
class RenderedTemplate:
    content: bytes
    metadata: dict[str, Any]
    warnings: list[str]


def _flatten_context(context: Mapping[str, Any], prefix: str = "") -> dict[str, Any]:
    flattened: dict[str, Any] = {}
    for key, value in context.items():
        name = f"{prefix}.{key}" if prefix else str(key)
        flattened[name] = value
        if isinstance(value, Mapping):
            flattened.update(_flatten_context(value, name))
    return flattened


def _fallback_context(context: Mapping[str, Any], warnings: list[str]) -> dict[str, Any]:
    data = _coerce_mapping(context)

    class _FallbackDict(dict):
        def __missing__(self, key: str) -> Any:
            warnings.append(f"missing context key: {key}")
            return ""

    fallback = _FallbackDict()
    for key, value in data.items():
        fallback[key] = _fallback_context(value, warnings) if isinstance(value, Mapping) else value
    return fallback


def render_docx_with_metadata(template_bytes: bytes, context: Mapping[str, Any] | None) -> RenderedTemplate:
    render_context = _coerce_mapping(context)
    warnings: list[str] = []
    if not render_context:
        warnings.append("rendered with empty context")

    tpl = DocxTemplate(BytesIO(template_bytes))
    strict_env = Environment(undefined=StrictUndefined)
    try:
        tpl.render(render_context, jinja_env=strict_env)
    except UndefinedError:
        fallback = _fallback_context(render_context, warnings)
        tpl = DocxTemplate(BytesIO(template_bytes))
        tpl.render(fallback)
        warnings.append("strict render failed; empty-string fallback applied")
    buffer = BytesIO()
    tpl.save(buffer)
    content = buffer.getvalue()
    context_json = json.dumps(render_context, ensure_ascii=False, sort_keys=True, default=str)
    metadata = {
        "template_sha256": hashlib.sha256(template_bytes).hexdigest(),
        "output_sha256": hashlib.sha256(content).hexdigest(),
        "context_sha256": hashlib.sha256(context_json.encode("utf-8")).hexdigest(),
        "context_keys": sorted(_flatten_context(render_context).keys()),
        "warnings": list(warnings),
        "engine": "docxtpl",
        "rendered_at": json.dumps({"utc": "deterministic"}),
        "reproducibility": {
            "context_sha256": hashlib.sha256(context_json.encode("utf-8")).hexdigest(),
            "template_sha256": hashlib.sha256(template_bytes).hexdigest(),
            "context_bytes": len(context_json.encode("utf-8")),
        },
    }
    return RenderedTemplate(content=content, metadata=metadata, warnings=warnings)


def render_docx(template_bytes: bytes, context: Mapping[str, Any] | None) -> bytes:
    return render_docx_with_metadata(template_bytes, context).content


@dataclass
class TemplateRenderer:
    template_path: str

    def render(self, context: Mapping[str, Any], output_path: str) -> str:
        rendered = render_docx_with_metadata(Path(self.template_path).read_bytes(), context)
        Path(output_path).write_bytes(rendered.content)
        return output_path
