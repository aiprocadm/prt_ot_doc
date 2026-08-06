#!/usr/bin/env python
"""Robust route migration using AST."""

import ast
from pathlib import Path

ROUTES_DIR = Path("/workspaces/prt_ot_doc/backend/app/api/routes")
SKIP = {"tenants.py", "health.py", "ws_stub.py", "items.py", "outbox_admin.py"}


def get_imports_end_line(tree):
    """Find the line number of the last import statement."""
    last_import_lineno = 0

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            last_import_lineno = max(last_import_lineno, node.end_lineno or node.lineno)

    return last_import_lineno


def parse_and_add_imports(filepath: Path) -> bool:
    """Parse file and add required imports."""
    with open(filepath, "r") as f:
        content = f.read()

    # Check if already has new imports
    if "PermissionChecker" in content and "TenantContextValidator" in content:
        return False

    try:
        tree = ast.parse(content)
    except SyntaxError:
        return False

    # Find last import line number (1-indexed)
    last_import_line = get_imports_end_line(tree)
    if last_import_line == 0:
        return False

    lines = content.split("\n")

    # Find where to insert (after the last import line)
    insert_idx = last_import_line  # 0-indexed, so this is right after

    # Check what to add
    new_imports = []
    if "PermissionChecker" not in content:
        new_imports.append("from app.core.permission_checker import PermissionChecker")
    if "TenantContextValidator" not in content:
        new_imports.append("from app.core.tenant_validation import TenantContextValidator")
    if "get_correlation_id" not in content and "get_session" in content:
        # Update the existing get_session import
        for i in range(last_import_line):
            if "from app.api.dependencies import" in lines[i] and "get_session" in lines[i]:
                if "get_correlation_id" not in lines[i]:
                    lines[i] = lines[i].replace("get_session,", "get_correlation_id, get_session,")
                break

    if not new_imports:
        return False

    # Insert new imports
    for idx, imp in enumerate(new_imports):
        lines.insert(insert_idx + idx, imp)

    new_content = "\n".join(lines)

    # Verify the result is valid Python
    try:
        ast.parse(new_content)
    except SyntaxError:
        print(f"  ERROR: Modified file has syntax errors: {filepath.name}")
        return False

    # Write back
    with open(filepath, "w") as f:
        f.write(new_content)

    return True


def main():
    """Migrate all routes."""
    all_files = sorted([f for f in ROUTES_DIR.glob("*.py") if not f.name.startswith("_")])

    migrated = 0
    skipped = 0
    errors = 0

    for filepath in all_files:
        if filepath.name in SKIP:
            skipped += 1
            continue

        try:
            if parse_and_add_imports(filepath):
                print(f"✓ {filepath.name}")
                migrated += 1
            else:
                skipped += 1
        except Exception as e:
            print(f"✗ {filepath.name}: {e}")
            errors += 1

    print(f"\n✓ Migrated: {migrated}, ⊘ Skipped: {skipped}, ✗ Errors: {errors}")
    return True


if __name__ == "__main__":
    main()
