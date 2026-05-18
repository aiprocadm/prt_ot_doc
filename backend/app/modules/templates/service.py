from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.core.utils.canonical_hash import compute_sha256_input
from app.modules.templates.linter import (
    inspect_template_context as _inspect_template_context,
    lint_template,
)
from app.modules.templates.render import render_docx


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
    sample_schema: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return lint_template(
        docx_bytes,
        required_fields=required_fields,
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


def render_preview_docx(*, template_bytes: bytes, data: dict[str, Any], passport: dict[str, Any], visible_passport: bool = False) -> bytes:
    return render_docx(template_bytes, data, passport, visible_passport=visible_passport)
