"""Template migration / quality audit (Phase 5.1 / vNext-DOC-02).

Bulk-scans existing template versions, runs the hardened linter against each
DOCX payload, and produces a structured report listing every version with
its errors, warnings and summary counts. Used by:

- ``POST /api/v1/templates/audit`` (admin-only) — on-demand audit.
- ``scripts/audit/validate_templates.py`` — CLI for CI / scheduled runs.

The service intentionally does not mutate the DB; it only reads and reports.
The optional ``persist=True`` flag may be added later to write the linter
report back into ``TemplateVersion.linter_report_json`` for caching, but the
default is to keep the audit side-effect-free so it can run safely against
production data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Template, TemplateVersion

from .linter import lint_template

BytesLoader = Callable[[str], bytes]


@dataclass
class TemplateVersionAudit:
    """Audit result for one ``(Template, TemplateVersion)`` pair."""

    template_id: str
    template_code: str | None
    template_name: str
    tenant_id: str
    version_id: str
    version_number: int
    status: str
    file_key: str | None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    summary: dict[str, int] = field(default_factory=dict)
    load_error: str | None = None

    @property
    def severity(self) -> str:
        if self.load_error or self.errors:
            return "error"
        if self.warnings:
            return "warning"
        return "ok"

    def to_dict(self) -> dict[str, Any]:
        return {
            "template_id": self.template_id,
            "template_code": self.template_code,
            "template_name": self.template_name,
            "tenant_id": self.tenant_id,
            "version_id": self.version_id,
            "version_number": self.version_number,
            "status": self.status,
            "file_key": self.file_key,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "summary": dict(self.summary),
            "load_error": self.load_error,
            "severity": self.severity,
        }


@dataclass
class TemplateAuditReport:
    """Aggregate audit across many template versions."""

    items: list[TemplateVersionAudit] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.items)

    @property
    def total_errors(self) -> int:
        return sum(1 for item in self.items if item.errors or item.load_error)

    @property
    def total_warnings(self) -> int:
        return sum(1 for item in self.items if item.warnings and not item.errors)

    @property
    def total_ok(self) -> int:
        return sum(1 for item in self.items if item.severity == "ok")

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": {
                "total": self.total,
                "ok": self.total_ok,
                "warnings": self.total_warnings,
                "errors": self.total_errors,
            },
            "items": [item.to_dict() for item in self.items],
        }


def _file_key(version: TemplateVersion) -> str | None:
    return version.file_id or version.payload_key or None


async def audit_template_versions(
    session: AsyncSession,
    *,
    tenant_id: str | None = None,
    loader: BytesLoader,
    template_id: str | None = None,
) -> TemplateAuditReport:
    """Audit every non-deleted template version.

    Args:
        session: Async SQLAlchemy session.
        tenant_id: When provided, limits the scan to one tenant. Required by
            the per-tenant admin endpoint; the CLI may pass ``None`` for a
            cross-tenant sweep.
        loader: Synchronous ``key -> bytes`` callable for retrieving DOCX
            payload bytes. Tests can pass an in-memory dict-backed loader;
            production calls pass ``FileStorageService.default().get``.
        template_id: Optional narrowing to one template (useful for the
            admin "rerun this template's audit" action).

    Returns:
        :class:`TemplateAuditReport` with one item per scanned version. The
        report is safe to serialize to JSON and is intentionally a snapshot
        — no DB writes happen.
    """

    stmt = (
        select(Template, TemplateVersion)
        .join(TemplateVersion, TemplateVersion.template_id == Template.id)
        .where(Template.deleted_at.is_(None))
        .where(TemplateVersion.deleted_at.is_(None))
        .order_by(Template.tenant_id, Template.code, TemplateVersion.version)
    )
    if tenant_id is not None:
        stmt = stmt.where(Template.tenant_id == tenant_id)
    if template_id is not None:
        stmt = stmt.where(Template.id == template_id)

    rows = (await session.execute(stmt)).all()

    report = TemplateAuditReport()
    for template, version in rows:
        key = _file_key(version)
        item = TemplateVersionAudit(
            template_id=template.id,
            template_code=template.code,
            template_name=template.name,
            tenant_id=template.tenant_id,
            version_id=version.id,
            version_number=version.version,
            status=version.status.value if hasattr(version.status, "value") else str(version.status),
            file_key=key,
        )
        if not key:
            item.load_error = "MISSING_FILE_KEY"
            report.items.append(item)
            continue
        try:
            payload = loader(key)
        except Exception as exc:  # pragma: no cover - depends on storage backend
            item.load_error = f"FILE_LOAD_FAILED: {exc.__class__.__name__}"
            report.items.append(item)
            continue
        if not payload:
            item.load_error = "EMPTY_PAYLOAD"
            report.items.append(item)
            continue
        try:
            lint_report = lint_template(
                payload,
                sample_schema=version.required_fields_schema,
            )
        except Exception as exc:  # pragma: no cover - linter is hardened
            item.load_error = f"LINT_FAILED: {exc.__class__.__name__}: {exc}"
            report.items.append(item)
            continue
        item.errors = list(lint_report.get("errors", []))
        item.warnings = list(lint_report.get("warnings", []))
        item.summary = dict(lint_report.get("summary", {}))
        report.items.append(item)

    return report
