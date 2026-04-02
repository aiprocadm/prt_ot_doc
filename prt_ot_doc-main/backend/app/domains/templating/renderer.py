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

_RENDERER_VERSION = "templating.renderer.v2"


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


def _normalize_context(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _normalize_context(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_normalize_context(item) for item in value]
    if isinstance(value, tuple):
        return [_normalize_context(item) for item in value]
    if isinstance(value, set):
        return sorted(_normalize_context(item) for item in value)
    return value


def _fallback_context(context: Mapping[str, Any], warnings: list[str], *, path: str = "") -> dict[str, Any]:
    data = _coerce_mapping(context)

    class _FallbackDict(dict):
        def __missing__(self, key: str) -> Any:
            qualified = f"{path}.{key}" if path else key
            warnings.append(f"missing context key: {qualified}")
            return ""

    fallback = _FallbackDict()
    for key, value in data.items():
        child_path = f"{path}.{key}" if path else str(key)
        if isinstance(value, Mapping):
            fallback[key] = _fallback_context(value, warnings, path=child_path)
        elif isinstance(value, list):
            fallback[key] = [_normalize_context(item) for item in value]
        else:
            fallback[key] = value
    return fallback


def render_docx_with_metadata(template_bytes: bytes, context: Mapping[str, Any] | None) -> RenderedTemplate:
    raw_context = _coerce_mapping(context)
    render_context = _normalize_context(raw_context)
    warnings: list[str] = []
    if not render_context:
        warnings.append("rendered with empty context")

    tpl = DocxTemplate(BytesIO(template_bytes))
    strict_env = Environment(undefined=StrictUndefined)
    strict_mode_ok = True
    missing_keys: list[str] = []
    try:
        tpl.render(render_context, jinja_env=strict_env)
    except UndefinedError as exc:
        strict_mode_ok = False
        warnings.append(f"strict render failed: {exc}")
        fallback = _fallback_context(render_context, warnings)
        tpl = DocxTemplate(BytesIO(template_bytes))
        tpl.render(fallback)
        missing_keys = sorted({warning.removeprefix("missing context key: ") for warning in warnings if warning.startswith("missing context key:")})
        warnings.append("strict render failed; empty-string fallback applied")
    buffer = BytesIO()
    tpl.save(buffer)
    content = buffer.getvalue()
    context_json = json.dumps(render_context, ensure_ascii=False, sort_keys=True, default=str)
    flattened = _flatten_context(render_context)
    template_sha = hashlib.sha256(template_bytes).hexdigest()
    context_sha = hashlib.sha256(context_json.encode("utf-8")).hexdigest()
    output_sha = hashlib.sha256(content).hexdigest()
    metadata = {
        "template_sha256": template_sha,
        "output_sha256": output_sha,
        "context_sha256": context_sha,
        "context_keys": sorted(flattened.keys()),
        "warnings": list(warnings),
        "warnings_count": len(warnings),
        "missing_keys": missing_keys,
        "missing_keys_count": len(missing_keys),
        "engine": "docxtpl",
        "renderer_version": _RENDERER_VERSION,
        "strict_mode": strict_mode_ok,
        "rendered_at": "deterministic",
        "reproducibility": {
            "context_sha256": context_sha,
            "template_sha256": template_sha,
            "output_sha256": output_sha,
            "context_bytes": len(context_json.encode("utf-8")),
            "context_key_count": len(flattened),
            "template_bytes": len(template_bytes),
            "output_bytes": len(content),
            "renderer_version": _RENDERER_VERSION,
        },
        "context_summary": {
            "root_keys": sorted(render_context.keys()),
            "nested_keys": sorted(flattened.keys()),
            "root_key_count": len(render_context),
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
