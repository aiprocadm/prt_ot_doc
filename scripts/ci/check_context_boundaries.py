#!/usr/bin/env python3
"""ARCH-3 — enforce bounded-context import boundaries (no GitHub Actions needed).

The rule "do not mix bounded contexts directly" lives in
``backend/app/core/product_spec.py::ARCHITECTURE_RULES`` but was never enforced.
This check enforces it for the two legacy-coupling directions:

  * ``app.modules.*`` must not import ``app.domains.*``
  * ``app.domains.*`` must not import ``app.modules.*``

A NEW cross-context import fails the check. The current leaks (audit 2026-06-30:
8 modules→domains, 2 domains→modules) are frozen in ``ALLOWLIST`` — a temporary
debt list drained by ARCH-1 (domains/ → modules/ migration). The allowlist is
kept honest: a stale entry (no longer a real import) also fails the check.

Why a custom AST walker instead of import-linter: ``app.modules`` / ``app.domains``
are PEP 420 namespace packages (no ``__init__.py``), which import-linter's graph
builder (grimp) skips. The ТЗ allows "import-linter ИЛИ эквивалентный тест"; this
walker reads files directly (namespace-agnostic) and needs only the stdlib, so it
runs on any Python and inside the local gate.

NOTE: ``app.modules.* -> app.services.*`` is intentionally allowed — the ТЗ
designates ``services/`` as the sanctioned orchestration layer between contexts.

Run: ``make check-boundaries`` (also runs inside ``make gate`` / local_gate.py).
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
APP_DIR = BACKEND_DIR / "app"

# (importer_module, imported_from_module) edges that are tolerated for now.
# Each is a debt item for ARCH-1. ``imported_from_module`` is the module named in
# ``from X import ...`` / ``import X`` (X), not the imported attribute.
ALLOWLIST: set[tuple[str, str]] = {
    # modules → domains (11)
    ("app.modules.briefings.services", "app.domains.signing.pep"),
    ("app.modules.files.api", "app.domains.files"),
    ("app.modules.files.service", "app.domains.files"),
    # ARCH-4 slice 10: FileService god-class split relocated the same legitimate ``s3``
    # access into the package sub-modules — same debt item, not a new leak.
    ("app.modules.files.service._fileops", "app.domains.files"),
    ("app.modules.files.service._functions", "app.domains.files"),
    ("app.modules.files.service._uploads", "app.domains.files"),
    ("app.modules.files.storage", "app.domains.files"),
    ("app.modules.health_checks.service", "app.domains.files"),
    ("app.modules.pdf.convert", "app.domains.files"),
    ("app.modules.projections.services", "app.domains.contractors.lifecycle"),
    ("app.modules.templates.service", "app.domains.templating.renderer"),
    # domains → modules (2)
    ("app.domains.contractors.lifecycle", "app.modules.contractors.models"),
    ("app.domains.ppe.service", "app.modules.ppe.services"),
    # ARCH-1 compat-shims: canon logic moved to modules/, domains/<ctx> kept as a pure
    # re-export until the next major (POST-1 removes it). Intentional, not debt to reduce.
    ("app.domains.risk", "app.modules.risk.calc"),
    ("app.domains.risk.calc", "app.modules.risk.calc"),
    ("app.domains.incidents", "app.modules.incidents.operations"),
    ("app.domains.incidents.service", "app.modules.incidents.operations"),
}


def _module_name(path: Path) -> str:
    """backend/app/modules/files/service.py -> app.modules.files.service."""
    rel = path.relative_to(BACKEND_DIR).with_suffix("")
    parts = list(rel.parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _forbidden_target(context: str, imported: str) -> bool:
    """A file under ``app.<context>`` importing the *other* context is forbidden."""
    other = "app.domains." if context == "modules" else "app.modules."
    return imported.startswith(other)


def _imported_modules(node: ast.AST) -> list[str]:
    """Modules referenced by an import node (the ``X`` in ``from X import ...``)."""
    if isinstance(node, ast.ImportFrom):
        # Skip relative imports (level>0): they never cross app.modules/app.domains.
        if node.level == 0 and node.module:
            return [node.module]
        return []
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    return []


def scan() -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """Return (violations, stale_allowlist_entries)."""
    found: set[tuple[str, str]] = set()
    for context in ("modules", "domains"):
        ctx_dir = APP_DIR / context
        if not ctx_dir.is_dir():
            continue
        for py in sorted(ctx_dir.rglob("*.py")):
            if "__pycache__" in py.parts:
                continue
            importer = _module_name(py)
            try:
                tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
            except SyntaxError as exc:  # pragma: no cover - surfaces a real parse break
                print(f"WARN: cannot parse {py}: {exc}", file=sys.stderr)
                continue
            for node in ast.walk(tree):
                for imported in _imported_modules(node):
                    if _forbidden_target(context, imported):
                        found.add((importer, imported))

    violations = sorted(e for e in found if e not in ALLOWLIST)
    stale = sorted(ALLOWLIST - found)
    return violations, stale


def main() -> int:
    violations, stale = scan()
    ok = True
    if violations:
        ok = False
        print("✖ ARCH-3: new cross-context imports (forbidden — not in allowlist):")
        for importer, imported in violations:
            print(f"    {importer} -> {imported}")
        print(
            "\n  Route cross-context access through services/ or a module's public API,\n"
            "  or (if genuinely unavoidable) add the edge to ALLOWLIST in\n"
            "  scripts/ci/check_context_boundaries.py with a tracking note."
        )
    if stale:
        ok = False
        print("\n✖ ARCH-3: stale ALLOWLIST entries (import no longer exists — remove them):")
        for importer, imported in stale:
            print(f"    {importer} -> {imported}")
    if ok:
        print(
            f"✓ ARCH-3: bounded-context boundaries clean "
            f"({len(ALLOWLIST)} allowlisted legacy leaks, 0 new)."
        )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
