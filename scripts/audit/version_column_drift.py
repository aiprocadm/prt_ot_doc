"""Minimal audit: which tables inherit `version` from mixin but lack it in migrations.

Bypasses the heavy `app.db.base` import chain that hangs on Win+Py3.13.
Pure AST analysis of models.py + migrations/versions/*.py.

Usage:
    py -3 scripts/audit/version_column_drift.py
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MODELS_FILE = REPO_ROOT / "backend" / "app" / "models" / "models.py"
MIGRATIONS_DIR = REPO_ROOT / "backend" / "app" / "migrations" / "versions"

VERSIONED_BASES = {"TenantBaseModel", "SharedModel"}


def _find_versioned_tables() -> dict[str, str]:
    """Map {tablename: ClassName} for every class that inherits TenantBaseModel/SharedModel."""
    tree = ast.parse(MODELS_FILE.read_text(encoding="utf-8"))
    result: dict[str, str] = {}
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        bases = {b.id for b in node.bases if isinstance(b, ast.Name)}
        if not (bases & VERSIONED_BASES):
            continue
        # Look for __tablename__ = "..." assignment in class body.
        tablename = node.name.lower()  # default per declared_attr in base.py
        for sub in node.body:
            if (
                isinstance(sub, ast.Assign)
                and any(
                    isinstance(t, ast.Name) and t.id == "__tablename__"
                    for t in sub.targets
                )
                and isinstance(sub.value, ast.Constant)
                and isinstance(sub.value.value, str)
            ):
                tablename = sub.value.value
        result[tablename] = node.name
    return result


def _migration_creates_version(path: Path) -> set[str]:
    """Return set of tablenames where migration's upgrade() creates a `version` column."""
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src, filename=str(path))
    upgrade_fn = None
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "upgrade":
            upgrade_fn = node
            break
    if upgrade_fn is None:
        return set()
    tables_with_version: set[str] = set()
    for node in ast.walk(upgrade_fn):
        if not isinstance(node, ast.Call):
            continue
        # op.create_table("foo", sa.Column("version", ...), ...)
        func = node.func
        is_create = (
            (isinstance(func, ast.Attribute) and func.attr == "create_table")
            or (isinstance(func, ast.Name) and func.id == "create_table")
        )
        if not is_create or not node.args:
            continue
        first = node.args[0]
        if not (isinstance(first, ast.Constant) and isinstance(first.value, str)):
            continue
        tablename = first.value
        for col_call in node.args[1:]:
            if not isinstance(col_call, ast.Call):
                continue
            cf = col_call.func
            ends_column = (
                (isinstance(cf, ast.Attribute) and cf.attr == "Column")
                or (isinstance(cf, ast.Name) and cf.id == "Column")
            )
            if not ends_column or not col_call.args:
                continue
            first_arg = col_call.args[0]
            if (
                isinstance(first_arg, ast.Constant)
                and isinstance(first_arg.value, str)
                and first_arg.value == "version"
            ):
                tables_with_version.add(tablename)
    # Also scan op.add_column("foo", sa.Column("version", ...)) and batch variants.
    for node in ast.walk(upgrade_fn):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        is_add = (
            (isinstance(func, ast.Attribute) and func.attr == "add_column")
            or (isinstance(func, ast.Name) and func.id == "add_column")
        )
        if not is_add or len(node.args) < 2:
            continue
        tname_arg = node.args[0]
        col_arg = node.args[1]
        if not (
            isinstance(tname_arg, ast.Constant)
            and isinstance(tname_arg.value, str)
        ):
            # batch.add_column has 1 arg (column only); look for With ancestor.
            continue
        tablename = tname_arg.value
        if (
            isinstance(col_arg, ast.Call)
            and col_arg.args
            and isinstance(col_arg.args[0], ast.Constant)
            and col_arg.args[0].value == "version"
        ):
            tables_with_version.add(tablename)
    # batch_alter_table("foo") ... batch.add_column(sa.Column("version", ...))
    for node in ast.walk(upgrade_fn):
        if not isinstance(node, ast.With):
            continue
        for item in node.items:
            ctx = item.context_expr
            if not (
                isinstance(ctx, ast.Call)
                and (
                    (isinstance(ctx.func, ast.Attribute) and ctx.func.attr == "batch_alter_table")
                    or (isinstance(ctx.func, ast.Name) and ctx.func.id == "batch_alter_table")
                )
                and ctx.args
                and isinstance(ctx.args[0], ast.Constant)
                and isinstance(ctx.args[0].value, str)
            ):
                continue
            tablename = ctx.args[0].value
            for inner in ast.walk(node):
                if (
                    isinstance(inner, ast.Call)
                    and isinstance(inner.func, ast.Attribute)
                    and inner.func.attr == "add_column"
                    and inner.args
                    and isinstance(inner.args[0], ast.Call)
                    and inner.args[0].args
                    and isinstance(inner.args[0].args[0], ast.Constant)
                    and inner.args[0].args[0].value == "version"
                ):
                    tables_with_version.add(tablename)
    return tables_with_version


def _migration_table_renames(path: Path) -> dict[str, str]:
    """Return {old: new} for rename_table ops in upgrade()."""
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src, filename=str(path))
    renames: dict[str, str] = {}
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and (
                (isinstance(node.func, ast.Attribute) and node.func.attr == "rename_table")
                or (isinstance(node.func, ast.Name) and node.func.id == "rename_table")
            )
            and len(node.args) >= 2
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[1], ast.Constant)
        ):
            renames[node.args[0].value] = node.args[1].value
    return renames


def _all_migration_tables(path: Path) -> set[str]:
    """Tables that *any* op creates (used to detect critical / absent tables)."""
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src, filename=str(path))
    upgrade_fn = None
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "upgrade":
            upgrade_fn = node
    if upgrade_fn is None:
        return set()
    tables: set[str] = set()
    for node in ast.walk(upgrade_fn):
        if (
            isinstance(node, ast.Call)
            and (
                (isinstance(node.func, ast.Attribute) and node.func.attr == "create_table")
                or (isinstance(node.func, ast.Name) and node.func.id == "create_table")
            )
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            tables.add(node.args[0].value)
    return tables


def main() -> int:
    versioned = _find_versioned_tables()
    print(f"Versioned model classes (inherit TenantBaseModel/SharedModel): {len(versioned)}")

    has_version: set[str] = set()
    migration_tables: set[str] = set()
    renames: dict[str, str] = {}
    for path in sorted(MIGRATIONS_DIR.glob("*.py")):
        if path.name.startswith("__"):
            continue
        has_version |= _migration_creates_version(path)
        migration_tables |= _all_migration_tables(path)
        renames.update(_migration_table_renames(path))

    # Apply renames so model name finds historical creator.
    for old, new in renames.items():
        if old in has_version:
            has_version.add(new)
        if old in migration_tables:
            migration_tables.add(new)

    drift = []
    critical = []
    for table, klass in sorted(versioned.items()):
        if table not in migration_tables:
            critical.append((table, klass))
        elif table not in has_version:
            drift.append((table, klass))

    print()
    print(f"=== TABLES MISSING `version` IN MIGRATIONS (but model has it): {len(drift)} ===")
    for t, k in drift:
        print(f"  {t}  ({k})")
    print()
    print(f"=== CRITICAL (table not created by ANY migration): {len(critical)} ===")
    for t, k in critical:
        print(f"  {t}  ({k})")
    print()
    print(f"Total versioned model tables: {len(versioned)}")
    print(f"With `version` column in migrations: {len(versioned) - len(drift) - len(critical)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
