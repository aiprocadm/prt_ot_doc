from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.core.utils.canonical_hash import compute_sha256_input
from app.domains.templating.renderer import render_docx as _render_docx_production
from app.modules.templates.linter import (
    inspect_template_context as _inspect_template_context,
)
from app.modules.templates.linter import (
    lint_template,
)
from app.modules.templates.passport import inject_passport


def build_passport(
    *,
    code: str,
    version: int,
    tenant_id: str,
    generated_by: str,
    correlation_id: str,
    data: dict[str, Any],
    mapping: dict[str, Any] | None = None,
    options: dict[str, Any] | None = None,
    npa_binding_id: str | None = None,
    document_id: str | None = None,
    document_version_id: str | None = None,
    version_number: int | None = None,
) -> dict[str, Any]:
    return {
        "template_version": f"{code}:v{version}",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generated_by": generated_by,
        "tenant_id": tenant_id,
        "sha256_input": compute_sha256_input(
            data,
            mapping=mapping,
            template_version_id=f"{code}:{version}",
            options=options,
        ),
        "npa_binding_id": npa_binding_id,
        "correlation_id": correlation_id,
        "document_id": document_id,
        "document_version_id": document_version_id,
        "version_number": version_number,
    }


def lint_docx_template(
    docx_bytes: bytes,
    *,
    required_fields: list[str] | None = None,
    available_fields: list[str] | None = None,
    sample_schema: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return lint_template(
        docx_bytes,
        required_fields=required_fields,
        available_fields=available_fields,
    )
        sample_schema=sample_schema,
    )


def inspect_docx_template(
    docx_bytes: bytes,
    *,
    available_variables: dict[str, Any] | None = None,
    required_fields: list[str] | None = None,
) -> dict[str, Any]:
    return _inspect_template_context(
        docx_bytes,
        available_variables=available_variables,
        required_fields=required_fields,
    )


def render_preview_docx(
    *,
    template_bytes: bytes,
    data: dict[str, Any],
    passport: dict[str, Any],
    visible_passport: bool = False,
) -> bytes:
    """Render a template for preview using the same pipeline as final document
    generation.

def render_preview_docx(*, template_bytes: bytes, data: dict[str, Any], passport: dict[str, Any], visible_passport: bool = False) -> bytes:
    return render_docx(template_bytes, data, passport, visible_passport=visible_passport)


def inspect_template_variables(
    *,
    placeholder_index: dict[str, Any] | None,
    required_fields_schema: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compute a Variable Inspector report from a stored placeholder index.

    The caller (API layer) keeps the parse result in ``template_versions.placeholder_index``
    when the template is uploaded or re-linted, so this function intentionally
    does not touch storage — it operates on already-parsed metadata and the
    template version's JSON schema (``required_fields_schema``).
    """

    placeholders = placeholder_index or {}
    fields = list(placeholders.get("fields") or [])
    loops = list(placeholders.get("loops") or [])
    conditions = list(placeholders.get("conditions") or [])

    used_roots: set[str] = set()
    for field in fields:
        name = (field.get("name") or "").strip()
        if name:
            used_roots.add(name.split(".")[0])
    loop_vars = {(loop.get("var") or "").strip() for loop in loops if loop.get("var")}
    used_roots -= loop_vars

    schema = required_fields_schema or {}
    declared_required = [
        str(name)
        for name in (schema.get("required") or [])
        if isinstance(name, str) and name
    ]
    properties = schema.get("properties")
    declared_available = (
        sorted(str(name) for name in properties.keys() if isinstance(name, str) and name)
        if isinstance(properties, dict)
        else []
    )

    declared_available_set = set(declared_available)
    declared_required_set = set(declared_required)

    # `used_undeclared` only makes sense when the template version actually
    # advertises a schema with `properties`. If no schema is bound, the
    # template can use anything the rendering context provides.
    used_undeclared = (
        sorted(used_roots - declared_available_set)
        if declared_available
        else []
    )
    declared_unused = sorted(declared_required_set - used_roots)

    return {
        "used": fields,
        "loops": loops,
        "conditions": conditions,
        "declared_required": declared_required,
        "declared_available": declared_available,
        "coverage": {
            "used_undeclared": used_undeclared,
            "declared_unused": declared_unused,
            "used_count": len(used_roots),
            "declared_count": len(declared_available),
        },
    }
    Delegates to :func:`app.domains.templating.renderer.render_docx` (docxtpl
    based) followed by :func:`inject_passport`, mirroring the production
    document pipeline in ``app.tasks._core``. Keeping both paths on the same
    renderer is what makes the "preview matches final" acceptance contract
    true by construction — see ``tests/test_templates_preview_parity.py``.
    """
    rendered = _render_docx_production(template_bytes, data)
    return inject_passport(rendered, passport, visible=visible_passport)
