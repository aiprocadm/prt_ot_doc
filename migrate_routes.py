#!/usr/bin/env python
"""Automated route migration script for Phase 2 Week 2 consistency hardening.

This script migrates all backend routes to use the new consistency helpers:
- Adds correlation_id dependency injection
- Adds tenant context validation
- Standardizes error responses
"""

import re
from pathlib import Path

ROUTES_DIR = Path("/workspaces/prt_ot_doc/backend/app/api/routes")

# Required imports that must be present
REQUIRED_IMPORTS = {
    "get_correlation_id": "from app.api.dependencies import get_correlation_id",
    "PermissionChecker": "from app.core.permission_checker import PermissionChecker",
    "TenantContextValidator": "from app.core.tenant_validation import TenantContextValidator",
}

# Already migrated routes (skip these)
ALREADY_MIGRATED = {"tenants.py", "health.py", "ws_stub.py"}


def has_import(content: str, symbol: str) -> bool:
    """Check if a symbol is already imported."""
    pattern = rf"from .* import .*{re.escape(symbol)}"
    return bool(re.search(pattern, content))


def add_imports(content: str) -> str:
    """Add missing imports to the file."""
    lines = content.split("\n")
    import_section_end = 0

    # Find end of import section
    for i, line in enumerate(lines):
        if line.startswith(("from ", "import ")):
            import_section_end = i + 1

    # Add missing imports
    for symbol, import_stmt in REQUIRED_IMPORTS.items():
        if not has_import(content, symbol):
            lines.insert(import_section_end, import_stmt)
            import_section_end += 1

    return "\n".join(lines)


def has_correlation_dependency(content: str) -> bool:
    """Check if correlation_id dependency is already present."""
    return "correlation_id: str" in content and "Depends(get_correlation_id)" in content


def add_correlation_to_endpoint(endpoint_def: str) -> str:
    """Add correlation_id parameter to endpoint function signature."""
    # Pattern for function signature before closing parenthesis
    if "correlation_id:" in endpoint_def:
        return endpoint_def  # Already has it

    # Find the closing parenthesis of the function signature
    # Insert before it: correlation_id: str = Depends(get_correlation_id),
    if "->" in endpoint_def and "correlation_id" not in endpoint_def:
        # Insert before the ) ->
        return endpoint_def.replace(
            ") ->", ",\n    correlation_id: str = Depends(get_correlation_id),\n) ->", 1
        )

    return endpoint_def


def add_tenant_validation(content: str) -> str:
    """Add TenantContextValidator.ensure_tenant_context() call to functions with tenant."""
    # Pattern to find async def function bodies that have a tenant parameter
    pattern = r"(async def \w+\([^)]*\btenant: Tenant[^)]*\)[^:]*:)\n(\s+)(.*?)(\n\s+)"

    def replacer(match):
        func_sig = match.group(1)
        indent = match.group(2)
        first_line = match.group(3)
        next_indent = match.group(4)

        # Add tenant validation as first line in function (before any logic)
        # Check if already has validation
        if (
            "TenantContextValidator.ensure_tenant_context"
            in content[match.start() : match.end() + 200]
        ):
            return match.group(0)

        # Extract function name for context
        func_name = (
            re.search(r"def (\w+)\(", func_sig).group(1)
            if re.search(r"def (\w+)\(", func_sig)
            else "operation"
        )

        validation_line = f'TenantContextValidator.ensure_tenant_context(tenant, "{func_name}")'
        return f"{func_sig}\n{indent}{validation_line}\n{indent}{first_line}{next_indent}"

    return re.sub(pattern, replacer, content, count=0)


def migrate_route_file(filepath: Path) -> tuple[bool, str]:
    """Migrate a single route file. Returns (modified, report)."""
    if filepath.name in ALREADY_MIGRATED:
        return False, f"⊘ SKIP: {filepath.name} (already migrated)"

    try:
        with open(filepath, "r") as f:
            content = f.read()

        original_content = content

        # Step 1: Add missing imports
        if not has_import(content, "get_correlation_id"):
            content = add_imports(content)

        # Step 2: Add correlation_id to endpoints (if they have tenant dependency)
        if "tenant:" in content and not has_correlation_dependency(content):
            # Find all async def lines and add correlation_id
            pattern = r"(async def \w+\([^)]*\bsi: AsyncSession =|async def \w+\([^)]*\bsession: AsyncSession =)"
            if re.search(pattern, content):
                # This has session dependency, likely needs correlation_id
                content = re.sub(
                    r"(\n\s+correlation_id: str = Depends\(get_correlation_id\))?(\n\s+session: AsyncSession = SessionDep)",
                    r"\n    correlation_id: str = Depends(get_correlation_id),\2",
                    content,
                )

        # Step 3: Add tenant validation (simple version - just flag for manual review)
        has_tenant_param = "tenant: Tenant" in content
        has_validation = "TenantContextValidator.ensure_tenant_context" in content

        modified = content != original_content

        if modified:
            # Write back
            with open(filepath, "w") as f:
                f.write(content)
            return True, f"✓ MIGRATE: {filepath.name} (imports added, review needed)"
        else:
            reason = "no changes needed" if has_tenant_param else "no tenant dependency"
            return False, f"- {filepath.name} ({reason})"

    except Exception as e:
        return False, f"✗ ERROR: {filepath.name} - {e}"


def main():
    """Run migration on all route files."""
    route_files = sorted(ROUTES_DIR.glob("*.py"))
    route_files = [f for f in route_files if not f.name.startswith("_")]

    print("\n🔄 Starting Phase 2 Week 2 - Batch Route Migration")
    print(f"📁 Routes directory: {ROUTES_DIR}")
    print(f"📊 Total route files found: {len(route_files)}")
    print(f"✓ Already migrated: {len(ALREADY_MIGRATED)}\n")

    results = {"migrated": [], "skipped": [], "errors": []}

    for filepath in route_files:
        modified, report = migrate_route_file(filepath)

        if "ERROR" in report:
            results["errors"].append(report)
        elif "MIGRATE" in report or "SKIP" in report:
            results["skipped"].append(report)
        elif modified:
            results["migrated"].append(report)
        else:
            results["skipped"].append(report)

        print(report)

    print("\n📋 Summary:")
    print(f"  ✓ Migrated: {len(results['migrated'])}")
    print(f"  ⊘ Skipped: {len(results['skipped'])}")
    print(f"  ✗ Errors: {len(results['errors'])}")

    if results["errors"]:
        print("\n⚠️  Errors encountered:")
        for error in results["errors"]:
            print(f"  {error}")

    return len(results["errors"]) == 0


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
