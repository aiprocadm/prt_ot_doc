#!/usr/bin/env python
"""Proper route migration using AST parsing."""

import ast
from pathlib import Path

ROUTES_DIR = Path("/workspaces/prt_ot_doc/backend/app/api/routes")
ALREADY_MIGRATED = {"tenants.py", "health.py", "ws_stub.py"}


class RouteModifier(ast.NodeVisitor):
    """AST visitor to detect route structure."""
    
    def __init__(self):
        self.has_tenant = False
        self.has_correlation = False
        self.async_functions = []
    
    def visit_FunctionDef(self, node):
        # Check if function has tenant parameter
        for arg in node.args.args:
            if arg.arg == "tenant":
                self.has_tenant = True
                self.async_functions.append(node.name)
            if arg.arg == "correlation_id":
                self.has_correlation = True
        self.generic_visit(node)
    
    def visit_AsyncFunctionDef(self, node):
        # Same for async functions
        for arg in node.args.args:
            if arg.arg == "tenant":
                self.has_tenant = True
                self.async_functions.append(node.name)
            if arg.arg == "correlation_id":
                self.has_correlation = True
        self.generic_visit(node)


def add_imports_properly(content: str) -> str:
    """Add imports to the correct position in the file."""
    lines = content.split('\n')
    
    # Find the end of all imports
    last_import_idx = -1
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith(('from ', 'import ')) and not line.startswith(' '):
            last_import_idx = i
    
    if last_import_idx == -1:
        # No imports found, shouldn't happen
        return content
    
    new_imports = [
        "from app.api.dependencies import get_correlation_id",
        "from app.core.permission_checker import PermissionChecker",
        "from app.core.tenant_validation import TenantContextValidator",
    ]
    
    # Check which imports are already present
    existing_imports = '\n'.join(lines)
    imports_to_add = []
    for imp in new_imports:
        symbol = imp.split()[-1]
        if symbol not in existing_imports:
            imports_to_add.append(imp)
    
    if not imports_to_add:
        return content
    
    # Insert imports after last import
    for idx, imp in enumerate(imports_to_add):
        lines.insert(last_import_idx + 1 + idx, imp)
    
    return '\n'.join(lines)


def migrate_file(filepath: Path) -> bool:
    """Migrate a file properly."""
    if filepath.name in ALREADY_MIGRATED:
        return False
    
    try:
        with open(filepath, 'r') as f:
            content = f.read()
        
        # Parse to check structure
        try:
            tree = ast.parse(content)
            modifier = RouteModifier()
            modifier.visit(tree)
        except SyntaxError:
            # If can't parse, skip
            return False
        
        # Only migrate if has tenant but not correlation_id yet
        if not modifier.has_tenant or modifier.has_correlation:
            return False
        
        original = content
        # Add imports
        content = add_imports_properly(content)
        
        if content != original:
            with open(filepath, 'w') as f:
                f.write(content)
            return True
    
    except Exception as e:
        print(f"Error: {filepath.name} - {e}")
        return False
    
    return False


def main():
    """Apply migrations."""
    route_files = sorted([f for f in ROUTES_DIR.glob("*.py") if not f.name.startswith("_")])
    
    migrated = 0
    
    for fp in route_files:
        if migrate_file(fp):
            print(f"✓ {fp.name}")
            migrated += 1
    
    print(f"\nMigrated: {migrated} files")
    return migrated > 0


if __name__ == "__main__":
    main()
