#!/usr/bin/env python3
"""Bulk template audit CLI (Phase 5.1 / vNext-DOC-02).

Runs ``app.modules.templates.audit_template_versions`` against every
non-deleted template version in the database and prints a JSON or
human-readable report. Intended for scheduled / CI runs.

Usage:
    python scripts/audit/validate_templates.py
    python scripts/audit/validate_templates.py --tenant demo --format json
    python scripts/audit/validate_templates.py --fail-on warning

Exit codes:
    0 — no errors (warnings allowed unless ``--fail-on warning`` is set).
    1 — at least one template version has errors or a load failure
        (or warnings, when ``--fail-on warning``).
    2 — configuration / runtime failure (DB unreachable, etc.).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

# Make `app.*` importable when the script is invoked from repo root.
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
BACKEND = REPO_ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit DOCX templates in the DB.")
    parser.add_argument("--tenant", help="Limit to one tenant slug or id (default: all tenants).")
    parser.add_argument(
        "--template",
        help="Limit to one template id (useful for re-running a single failing template).",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format. JSON is suitable for CI / programmatic consumers.",
    )
    parser.add_argument(
        "--fail-on",
        choices=("error", "warning"),
        default="error",
        help="Lowest severity that produces a non-zero exit code (default: error).",
    )
    return parser.parse_args(argv)


def _format_text(report_dict: dict) -> str:
    summary = report_dict["summary"]
    lines = [
        "Template audit report",
        "=" * 50,
        f"Total versions scanned : {summary['total']}",
        f"  OK                   : {summary['ok']}",
        f"  Warnings only        : {summary['warnings']}",
        f"  Errors / load fails  : {summary['errors']}",
        "",
    ]
    if not report_dict["items"]:
        lines.append("No template versions to audit.")
        return "\n".join(lines)

    by_severity = {"error": [], "warning": [], "ok": []}
    for item in report_dict["items"]:
        by_severity[item["severity"]].append(item)

    for severity in ("error", "warning", "ok"):
        bucket = by_severity[severity]
        if not bucket:
            continue
        lines.append(f"-- {severity.upper()} ({len(bucket)})")
        for item in bucket:
            head = (
                f"  {item['template_code'] or item['template_name']} "
                f"v{item['version_number']} "
                f"(tenant={item['tenant_id']}, version_id={item['version_id']})"
            )
            lines.append(head)
            if item["load_error"]:
                lines.append(f"    load_error: {item['load_error']}")
            for err in item["errors"]:
                lines.append(f"    error: {err}")
            for warn in item["warnings"]:
                lines.append(f"    warning: {warn}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


async def _run(args: argparse.Namespace) -> int:
    from app.db.session import AsyncSessionLocal
    from app.modules.templates import audit_template_versions
    from app.services.file_storage import FileStorageService

    storage = FileStorageService.default()

    session = AsyncSessionLocal(tenant=args.tenant) if args.tenant else AsyncSessionLocal()
    try:
        report = await audit_template_versions(
            session,
            tenant_id=args.tenant,
            loader=storage.get,
            template_id=args.template,
        )
    finally:
        await session.close()

    payload = report.to_dict()
    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(_format_text(payload))

    if args.fail_on == "error":
        return 1 if payload["summary"]["errors"] > 0 else 0
    # fail_on == "warning"
    has_problem = payload["summary"]["errors"] > 0 or payload["summary"]["warnings"] > 0
    return 1 if has_problem else 0


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        return asyncio.run(_run(args))
    except Exception as exc:  # noqa: BLE001 - top-level CLI safety net
        print(f"ERROR: audit failed: {exc.__class__.__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
