#!/usr/bin/env python
"""Advanced route migration - actually applies changes to files."""

import re
from pathlib import Path

ROUTES_DIR = Path("/workspaces/prt_ot_doc/backend/app/api/routes")
ALREADY_MIGRATED = {"tenants.py", "health.py", "ws_stub.py"}


def ensure_imports(content: str) -> str:
    """Ensure all required imports are present."""
    lines = content.split("\n")

    # Find import section end
    import_end = 0
    for i, line in enumerate(lines):
        if line.startswith(("from ", "import ")) or line.strip() == "":
            import_end = i + 1

    required_imports = [
        ("get_correlation_id", "from app.api.dependencies import get_correlation_id"),
        ("PermissionChecker", "from app.core.permission_checker import PermissionChecker"),
        ("TenantContextValidator", "from app.core.tenant_validation import TenantContextValidator"),
    ]

    for symbol, import_stmt in required_imports:
        # Check if already imported
        if not any(symbol in line for line in lines):
            # Add import
            lines.insert(import_end, import_stmt)
            import_end += 1

    return "\n".join(lines)


def add_correlation_id_to_endpoints(content: str) -> str:
    """Add correlation_id: str = Depends(get_correlation_id) to all async endpoints with tenant."""

    # Find all async def function definitions that have tenant parameter
    # Pattern: async def name(...tenant: Tenant...) -> ...:

    def add_to_func(match):
        func_def = match.group(0)

        # Skip if already has correlation_id
        if "correlation_id:" in func_def:
            return func_def

        # Find the position right before ") ->"
        if ") ->" not in func_def:
            return func_def

        # Insert correlation_id parameter before closing )
        # Find last comma before ) ->
        insert_point = func_def.rfind(",\n", 0, func_def.find(") ->"))
        if insert_point == -1:
            insert_point = func_def.rfind(", ", 0, func_def.find(") ->"))

        if insert_point > 0:
            # There's already a parameter, add after it
            indent_match = re.search(r"\n(\s+)", func_def[insert_point:])
            if indent_match:
                indent = indent_match.group(1)
                return (
                    func_def[:insert_point]
                    + ",\n"
                    + indent
                    + "correlation_id: str = Depends(get_correlation_id)"
                    + func_def[insert_point:]
                )

        # Single-line function def
        if ") ->" in func_def:
            return func_def.replace(
                ") ->", ",\n    correlation_id: str = Depends(get_correlation_id),\n) ->", 1
            )

        return func_def

    # Match async def ... tenant: Tenant ... ->
    pattern = r"async def \w+\([^)]*\btenant: Tenant[^)]*\) ->[^:]+"
    return re.sub(pattern, add_to_func, content)


def add_tenant_validation(content: str) -> str:
    """Add TenantContextValidator.ensure_tenant_context() calls."""

    # Pattern to find function bodies with tenant parameter
    # Find: async def function_name(...):
    # And: if tenant parameter exists
    # Add first line: TenantContextValidator.ensure_tenant_context(tenant, "function_name")

    def add_validation(match):
        func_decl = match.group(1)
        colon = match.group(2)
        first_body_indent = match.group(3)
        first_body_content = match.group(4)

        # Check if validation already exists
        if "TenantContextValidator.ensure_tenant_context" in first_body_content:
            return match.group(0)

        # Extract function name
        func_name_match = re.search(r"def (\w+)\(", func_decl)
        func_name = func_name_match.group(1) if func_name_match else "operation"

        validation = f'{first_body_indent}TenantContextValidator.ensure_tenant_context(tenant, "{func_name}")\n'

        return f"{func_decl}{colon}\n{validation}{first_body_indent}{first_body_content}"

    # Match: async def name(...tenant: Tenant...): followed by first statement
    pattern = r"(async def \w+\([^)]*\btenant: Tenant[^)]*\))(:)\n(\s+)(\S.*)"
    return re.sub(pattern, add_validation, content)


def migrate_file(filepath: Path) -> bool:
    """Migrate a single file. Returns True if modified."""
    if filepath.name in ALREADY_MIGRATED:
        return False

    with open(filepath, "r") as f:
        original = f.read()

    content = original

    # Step 1: Ensure imports
    content = ensure_imports(content)

    # Step 2: Add correlation_id if has tenant
    if "tenant:" in content:
        content = add_correlation_id_to_endpoints(content)
        content = add_tenant_validation(content)

    if content != original:
        with open(filepath, "w") as f:
            f.write(content)
        return True

    return False


def main():
    """Apply migrations."""
    route_files = sorted([f for f in ROUTES_DIR.glob("*.py") if not f.name.startswith("_")])

    migrated = 0
    skipped = 0

    for filepath in route_files:
        if migrate_file(filepath):
            print(f"✓ {filepath.name}")
            migrated += 1
        else:
            print(f"⊘ {filepath.name}")
            skipped += 1

    print(f"\n✓ Migrated: {migrated}, ⊘ Skipped: {skipped}")
    return migrated > 0


if __name__ == "__main__":
    main()
