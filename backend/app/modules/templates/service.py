from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from app.modules.templates.linter import lint_template
from app.modules.templates.render import render_docx


def build_passport(*, code: str, version: int, tenant_id: str, generated_by: str, correlation_id: str, data: dict[str, Any]) -> dict[str, Any]:
    canonical = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {
        "template_code": code,
        "template_version": version,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generated_by": generated_by,
        "tenant_id": tenant_id,
        "sha256_input_data": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "npa_binding_id": None,
        "correlation_id": correlation_id,
    }


def lint_docx_template(docx_bytes: bytes) -> dict[str, Any]:
    return lint_template(docx_bytes)


def render_preview_docx(*, template_bytes: bytes, data: dict[str, Any], passport: dict[str, Any], visible_passport: bool = False) -> bytes:
    return render_docx(template_bytes, data, passport, visible_passport=visible_passport)
