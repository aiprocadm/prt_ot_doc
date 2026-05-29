"""Audit ORM↔migration drift in this repository.

Surfaces the bug class fixed by iter-21 / PR #589 (RB-002i): a column declared
in a SQLAlchemy model with no paired Alembic migration. SQLite tests pass
because they build the schema via ``Base.metadata.create_all()``; Postgres
deployments fail at runtime when ORM queries reference the missing column.

Strategy:
  1. Import the same ``ALEMBIC_METADATA`` Alembic uses for autogenerate
     (this is the authoritative model-side schema).
  2. Parse every migration file under ``backend/app/migrations/versions/``
     using ``ast`` to extract all ``op.create_table``, ``op.add_column``,
     ``op.drop_column``, ``op.rename_table`` and ``alter_column(...,
     new_column_name=...)`` (column rename) calls. Build a ``(table, column)``
     set representing what migrations actually create.
  3. Diff: model columns not in migration set → drift.

Limitations:
  - Detects column-level drift only. FK and index drift would require
    walking ``op.create_foreign_key`` / ``op.create_index``.
  - Misses columns created via raw ``op.execute("ALTER TABLE ... ADD COLUMN
    ...")`` (the repo does not use this pattern for additions today; if a
    future migration does, the column will be flagged as a false positive).
  - Treats ``schema`` parameters as opaque — a table with the same name in
    ``app_shared`` vs tenant schema is collapsed into one entry. Matches
    how the ORM models declare them (no schema= on the Mapped class).
  - Column renames are recognized only in the ``with op.batch_alter_table(...)``
    form (``batch.alter_column("old", new_column_name="new")``) — the form
    every rename in the repo uses today. A bare top-level
    ``op.alter_column("table", "old", new_column_name="new")`` is NOT tracked;
    if a future migration uses it, the old name lingers in the migration set
    while the model declares the new one — the same business false-positive
    iter-45 closed for the batch form. Promote it to a batch block, or extend
    the generic Call-walker, when such a migration is introduced.

Usage::

    py -3 scripts/audit/check_orm_migration_drift.py
    py -3 scripts/audit/check_orm_migration_drift.py --json > drift.json
    py -3 scripts/audit/check_orm_migration_drift.py --severity critical
    py -3 scripts/audit/check_orm_migration_drift.py --summary

Severity classification (per drifting table):

- ``critical``: model has columns but NO migration creates the table at all.
  This is the iter-23 RefreshSession / SecurityAuditLog class — fix needs
  a full ``op.create_table(...)`` migration.
- ``business``: migration creates the table but model has substantive
  business columns missing. Fix needs ``op.add_column(...)`` for each.
- ``mixin``: migration creates the table but only ``TenantBaseModel`` /
  ``VersionedMixin`` / ``TimestampMixin`` columns are missing. Often this
  is a legacy migration written before the model adopted the mixin; fix
  is ``op.add_column(...)`` with sensible defaults.
- ``rename``: model and migration disagree on table name (singular vs
  plural is the common case — ``site`` vs ``sites``). Almost always a
  false positive from the audit's flat-namespace assumption.
- ``unloaded_model``: migration creates a table but no ORM model is
  registered with that name. Either the model module isn't imported in
  ``app.db.base`` or the table is genuinely orphaned.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import sys
import tempfile
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
MIGRATIONS_DIR = BACKEND_ROOT / "app" / "migrations" / "versions"


def _bootstrap_env() -> None:
    """Set the env vars the model imports need (mirrors tests/conftest.py)."""
    os.environ.setdefault("APP_NAME", "DriftAudit")
    os.environ.setdefault("APP_TRUSTED_HOSTS", "localhost,127.0.0.1,testserver")
    os.environ.setdefault("DEFAULT_LOCALE", "en-US")
    os.environ.setdefault("LIBREOFFICE_BIN", sys.executable)
    db_path = Path(tempfile.gettempdir()) / "prt_drift_audit.db"
    os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    os.environ.setdefault("REDIS_URL", "memory://")
    os.environ.setdefault("REDIS_RESULT_URL", "cache+memory://")
    os.environ.setdefault("RATE_LIMIT_STORAGE_URI", "memory://")
    os.environ.setdefault("S3_ENDPOINT", "http://localhost")
    os.environ.setdefault("SECRET_KEY", "drift-audit-not-for-production")
    os.environ.setdefault("S3_ACCESS_KEY", "audit")
    os.environ.setdefault("S3_SECRET_KEY", "audit")
    os.environ.setdefault("S3_BUCKET", "audit")
    # crypt stub for Windows / slim containers (passlib import).
    import types

    sys.modules.setdefault(
        "crypt", types.SimpleNamespace(crypt=lambda secret, salt: "mocked")
    )


def _load_model_columns() -> dict[str, set[str]]:
    """Return ``{table_name: {column_name, ...}}`` from ALEMBIC_METADATA."""
    # ``backend`` must be on sys.path for ``app.*`` imports to resolve.
    sys.path.insert(0, str(BACKEND_ROOT))
    from app.db.base import ALEMBIC_METADATA  # type: ignore[import-not-found]

    model_columns: dict[str, set[str]] = {}
    for table in ALEMBIC_METADATA.tables.values():
        # Strip schema prefix so "app_shared.user" and "user" collapse.
        name = table.name
        model_columns.setdefault(name, set()).update(c.name for c in table.columns)
    return model_columns


def _string_arg(node: ast.expr | None) -> str | None:
    """Extract a string literal from an AST argument; ``None`` if not a string."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _columns_in_create_table(call: ast.Call) -> list[str]:
    """Extract column names from a ``sa.Column("name", ...)`` inside create_table.

    ``op.create_table("user", sa.Column("id", ...), sa.Column("email", ...), ...)``
    """
    columns: list[str] = []
    # First arg is table name; remaining positional args are columns / constraints.
    for arg in call.args[1:]:
        if isinstance(arg, ast.Call) and _call_target_endswith(arg, "Column"):
            if arg.args:
                col_name = _string_arg(arg.args[0])
                if col_name:
                    columns.append(col_name)
    return columns


def _call_target_endswith(call: ast.Call, suffix: str) -> bool:
    """True if the callee's attribute chain ends with ``suffix`` (case-sensitive)."""
    func = call.func
    if isinstance(func, ast.Attribute):
        return func.attr == suffix
    if isinstance(func, ast.Name):
        return func.id == suffix
    return False


def _find_function(tree: ast.Module, name: str) -> ast.FunctionDef | None:
    """Locate a top-level function by name (None if absent)."""
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    return None


def _all_functions(tree: ast.Module) -> dict[str, ast.FunctionDef]:
    """Return ``{name: FunctionDef}`` for every top-level def in a module."""
    return {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}


def _column_names_in(nodes: Iterable[ast.AST]) -> list[str]:
    """Walk arbitrary AST nodes; collect every ``sa.Column("name", ...)``."""
    found: list[str] = []
    for root in nodes:
        for node in ast.walk(root):
            if (
                isinstance(node, ast.Call)
                and _call_target_endswith(node, "Column")
                and node.args
            ):
                name = _string_arg(node.args[0])
                if name:
                    found.append(name)
    return found


def _helper_extra_columns(
    func: ast.FunctionDef, functions: dict[str, ast.FunctionDef]
) -> list[str]:
    """Columns added unconditionally by a helper's own body.

    Walks ``func``'s body recursively; collects ``sa.Column("name", ...)``
    literals and inlines any helper calls (e.g. ``_base_columns()``).
    Used to model wrappers like::

        def _create_soft_table(name, *columns, unique=None):
            args = list(columns) + _base_columns() + [sa.Column("deleted_at", ...)]
            op.create_table(name, *args, ...)

    Returns the deleted_at + the columns returned from _base_columns().
    """
    extras: list[str] = []
    # Direct Column literals in the helper body.
    extras.extend(_column_names_in([func]))
    # Inline any same-module helpers the function calls.
    for node in ast.walk(func):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            callee = functions.get(node.func.id)
            if callee is not None and callee is not func:
                extras.extend(_column_names_in([callee]))
    # Deduplicate while preserving order.
    seen: set[str] = set()
    result: list[str] = []
    for name in extras:
        if name not in seen:
            seen.add(name)
            result.append(name)
    return result


def _table_creating_helpers(
    functions: dict[str, ast.FunctionDef],
) -> dict[str, list[str]]:
    """Identify helpers that ultimately call ``op.create_table``.

    Returns ``{helper_name: [extra_column_names_added_by_helper]}``.
    A helper qualifies if its body contains a call ending in
    ``create_table`` (e.g. ``op.create_table`` or ``self.create_table``).
    """
    helpers: dict[str, list[str]] = {}
    for name, func in functions.items():
        if name in ("upgrade", "downgrade"):
            continue
        creates_table = False
        for inner in ast.walk(func):
            if isinstance(inner, ast.Call) and _call_target_endswith(
                inner, "create_table"
            ):
                # Either direct op.create_table or recursive helper-of-helper.
                if (
                    isinstance(inner.func, ast.Attribute)
                    or isinstance(inner.func, ast.Name)
                    and inner.func.id != name
                ):
                    creates_table = True
                    break
        if creates_table:
            helpers[name] = _helper_extra_columns(func, functions)
    return helpers


def _parse_migration(path: Path) -> dict[str, object]:
    """Return ops extracted from one migration's ``upgrade()`` function only.

    We deliberately ignore ``downgrade()`` — its ``op.drop_column`` calls
    would otherwise cancel out the ``op.add_column`` from ``upgrade()``,
    producing false-positive drift. Forward-only history matches Alembic's
    actual production semantics (downgrade is dev-only convenience).

    Helper-function aware: calls to module-local helpers that wrap
    ``op.create_table`` (e.g. ``_create_soft_table(name, sa.Column(...), ...)``)
    are inlined so columns injected by the wrapper are counted too.
    """
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    upgrade_fn = _find_function(tree, "upgrade")
    walk_target: ast.AST = upgrade_fn if upgrade_fn is not None else tree

    functions = _all_functions(tree)
    helpers = _table_creating_helpers(functions)

    create_table: dict[str, list[str]] = defaultdict(list)
    add_column: dict[str, list[str]] = defaultdict(list)
    drop_column: dict[str, list[str]] = defaultdict(list)
    drop_table: list[str] = []
    rename_table: list[tuple[str, str]] = []  # (old, new)
    rename_column: list[tuple[str, str, str]] = []  # (table, old, new)

    # First: handle `with op.batch_alter_table("t", ...) as batch:` blocks.
    # These hold `batch.add_column(sa.Column("c", ...))` and `batch.drop_column("c")`
    # that the generic Call-walker can't associate with the right table.
    for node in ast.walk(walk_target):
        if not isinstance(node, ast.With):
            continue
        for item in node.items:
            ctx = item.context_expr
            if not (
                isinstance(ctx, ast.Call)
                and _call_target_endswith(ctx, "batch_alter_table")
                and ctx.args
            ):
                continue
            table_name = _string_arg(ctx.args[0])
            if not table_name:
                continue
            for inner in ast.walk(node):
                if not isinstance(inner, ast.Call):
                    continue
                # batch.add_column(sa.Column("col", ...))
                if _call_target_endswith(inner, "add_column") and inner.args:
                    col_arg = inner.args[0]
                    if (
                        isinstance(col_arg, ast.Call)
                        and _call_target_endswith(col_arg, "Column")
                        and col_arg.args
                    ):
                        col_name = _string_arg(col_arg.args[0])
                        if col_name:
                            add_column[table_name].append(col_name)
                # batch.drop_column("col")
                elif _call_target_endswith(inner, "drop_column") and inner.args:
                    col_name = _string_arg(inner.args[0])
                    if col_name:
                        drop_column[table_name].append(col_name)
                # batch.alter_column("old", new_column_name="new") — a rename.
                # Plain alter_column (type/nullable/server_default, no
                # new_column_name) is NOT a rename and is ignored.
                elif _call_target_endswith(inner, "alter_column") and inner.args:
                    old_name = _string_arg(inner.args[0])
                    new_name = next(
                        (
                            _string_arg(kw.value)
                            for kw in inner.keywords
                            if kw.arg == "new_column_name"
                        ),
                        None,
                    )
                    if old_name and new_name:
                        rename_column.append((table_name, old_name, new_name))

    for node in ast.walk(walk_target):
        if not isinstance(node, ast.Call):
            continue
        # Local helper that wraps op.create_table?
        if (
            isinstance(node.func, ast.Name)
            and node.func.id in helpers
            and node.args
        ):
            table_name = _string_arg(node.args[0])
            if table_name:
                # Columns passed positionally to the helper.
                create_table[table_name].extend(_columns_in_create_table(node))
                # Columns injected by helper's own body.
                create_table[table_name].extend(helpers[node.func.id])
            continue
        # op.create_table("name", Column(...), Column(...), ...)
        if _call_target_endswith(node, "create_table") and node.args:
            table_name = _string_arg(node.args[0])
            if table_name:
                create_table[table_name].extend(_columns_in_create_table(node))
        # op.add_column("table", sa.Column("col", ...))
        elif _call_target_endswith(node, "add_column") and len(node.args) >= 2:
            table_name = _string_arg(node.args[0])
            col_arg = node.args[1]
            if (
                table_name
                and isinstance(col_arg, ast.Call)
                and _call_target_endswith(col_arg, "Column")
                and col_arg.args
            ):
                col_name = _string_arg(col_arg.args[0])
                if col_name:
                    add_column[table_name].append(col_name)
        # op.drop_column("table", "col")
        elif _call_target_endswith(node, "drop_column") and len(node.args) >= 2:
            table_name = _string_arg(node.args[0])
            col_name = _string_arg(node.args[1])
            if table_name and col_name:
                drop_column[table_name].append(col_name)
        # op.drop_table("table")
        elif _call_target_endswith(node, "drop_table") and node.args:
            table_name = _string_arg(node.args[0])
            if table_name:
                drop_table.append(table_name)
        # op.rename_table("old", "new")
        elif _call_target_endswith(node, "rename_table") and len(node.args) >= 2:
            old_name = _string_arg(node.args[0])
            new_name = _string_arg(node.args[1])
            if old_name and new_name:
                rename_table.append((old_name, new_name))

    return {
        "create_table": dict(create_table),
        "add_column": dict(add_column),
        "drop_column": dict(drop_column),
        "drop_table": drop_table,
        "rename_table": rename_table,
        "rename_column": rename_column,
        "_path": str(path.relative_to(REPO_ROOT)),
    }


def _collect_migration_columns() -> tuple[dict[str, set[str]], list[dict[str, object]]]:
    """Walk all migrations; return aggregate ``{table: {col, ...}}`` + per-file ops.

    Aggregate ignores order; we do not attempt topological replay because the
    common drift case (column missing entirely) is order-independent.
    Dropped columns are subtracted; renamed tables map old→new table; renamed
    columns (alter_column new_column_name=) map old→new within a table.
    """
    all_files = sorted(MIGRATIONS_DIR.glob("*.py"))
    per_file: list[dict[str, object]] = []
    table_columns: dict[str, set[str]] = defaultdict(set)
    rename_map: dict[str, str] = {}
    column_renames: list[tuple[str, str, str]] = []  # (table, old, new), file order

    for path in all_files:
        if path.name.startswith("__"):
            continue
        ops = _parse_migration(path)
        per_file.append(ops)
        for table, cols in ops["create_table"].items():  # type: ignore[union-attr]
            table_columns[table].update(cols)
        for table, cols in ops["add_column"].items():  # type: ignore[union-attr]
            table_columns[table].update(cols)
        for old, new in ops["rename_table"]:  # type: ignore[union-attr]
            rename_map[old] = new
        column_renames.extend(ops["rename_column"])  # type: ignore[arg-type]

    # Apply renames so model's current name finds historical create_table.
    for old, new in rename_map.items():
        if old in table_columns:
            table_columns.setdefault(new, set()).update(table_columns.pop(old))

    # Apply column renames (alter_column new_column_name=). Done after the
    # table-rename merge so the rename resolves against the table's current
    # name, and before drop subtraction. Mirrors rename_table at column scope:
    # the old name yields to the new one the ORM model declares, so a renamed
    # column is not stranded as a false-positive drift entry.
    for table, old_col, new_col in column_renames:
        current = rename_map.get(table, table)
        cols = table_columns.get(current)
        if cols is not None:
            cols.discard(old_col)
            cols.add(new_col)

    # Subtract drops (must be done after rename merge).
    for ops in per_file:
        for table, cols in ops["drop_column"].items():  # type: ignore[union-attr]
            # If table was renamed after this drop, map to new name.
            current = rename_map.get(table, table)
            table_columns.get(current, set()).difference_update(cols)

    return dict(table_columns), per_file


# Columns injected by base mixins (``backend/app/models/base.py``). Drift
# limited to these is classified ``mixin`` severity — usually a legacy
# migration written before the model adopted the mixin.
_MIXIN_COLUMNS: frozenset[str] = frozenset(
    {
        "id",  # UUIDMixin
        "tenant_id",  # TenantBaseModel
        "created_at",  # TimestampMixin
        "updated_at",  # TimestampMixin
        "version",  # VersionedMixin
        "deleted_at",  # SoftDeleteMixin
    }
)


def _classify_severity(
    table: str,
    entry: dict[str, list[str]],
    model_tables: set[str],
    migration_tables: set[str],
) -> str:
    """Classify a drift entry by severity (see module docstring)."""
    model_only = entry.get("model_only") or []
    migration_only = entry.get("migration_only") or []

    in_model = table in model_tables
    in_migration = table in migration_tables

    # Migration only: an orphaned table the ORM never references.
    if not in_model and in_migration:
        return "unloaded_model"

    # Model only, no migration anywhere: must create the table.
    if in_model and not in_migration:
        return "critical"

    # Common rename pattern: singular/plural pair. Only flag if a DIFFERENT
    # table name (singular or plural variant) also exists in migrations —
    # the table comparing against itself does not count as a rename.
    if in_model and in_migration:
        candidates = {table.rstrip("s"), f"{table}s"} - {table}
        if any(c in migration_tables for c in candidates):
            return "rename"

    # Both exist; classify by what's missing.
    if model_only and not migration_only:
        # All-mixin missing → likely legacy migration retrofit.
        if all(col in _MIXIN_COLUMNS for col in model_only):
            return "mixin"
        return "business"
    if migration_only and not model_only:
        # Migration adds something the model doesn't have — probably stale
        # column that the model evolved past; safe but worth tracking.
        return "stale_migration_column"
    # Both sides have drift in opposite directions — substantive.
    return "business"


def _diff(
    model: dict[str, set[str]], migration: dict[str, set[str]]
) -> dict[str, dict[str, object]]:
    """Per-table column-level diff (model vs migration), with severity tag."""
    drift: dict[str, dict[str, object]] = {}
    all_tables = sorted(set(model) | set(migration))
    model_tables = set(model)
    migration_tables = set(migration)
    for table in all_tables:
        model_cols = model.get(table, set())
        mig_cols = migration.get(table, set())
        missing_in_migration = sorted(model_cols - mig_cols)
        missing_in_model = sorted(mig_cols - model_cols)
        if missing_in_migration or missing_in_model:
            entry: dict[str, object] = {}
            if missing_in_migration:
                entry["model_only"] = missing_in_migration
            if missing_in_model:
                entry["migration_only"] = missing_in_model
            entry["severity"] = _classify_severity(
                table, entry, model_tables, migration_tables  # type: ignore[arg-type]
            )
            drift[table] = entry
    return drift


def _format_text(drift: dict[str, dict[str, object]]) -> str:
    if not drift:
        return "OK: no ORM↔migration column drift detected."
    lines = [f"DRIFT: {len(drift)} table(s) with column-level mismatch.", ""]
    for table in sorted(drift):
        entry = drift[table]
        severity = entry.get("severity", "?")
        lines.append(f"  [{severity}] {table}:")
        model_only = entry.get("model_only")
        if model_only:
            lines.append(
                f"    model_only (in model, no migration creates it): "
                f"{', '.join(model_only)}"  # type: ignore[arg-type]
            )
        migration_only = entry.get("migration_only")
        if migration_only:
            lines.append(
                f"    migration_only (in migration, not on model): "
                f"{', '.join(migration_only)}"  # type: ignore[arg-type]
            )
    lines.append("")
    lines.append(
        "Hint: each `[critical]`/`[business]` model_only column needs an "
        "`op.add_column(...)` or `op.create_table(...)` migration "
        "(cf. iter-21 user.company_id / iter-23 refresh_session+securityauditlog)."
    )
    return "\n".join(lines)


def _format_summary(drift: dict[str, dict[str, object]]) -> str:
    """One-line-per-severity rollup. Useful for triaging large drift sets."""
    if not drift:
        return "OK: no ORM↔migration column drift detected."
    buckets: dict[str, list[str]] = defaultdict(list)
    for table, entry in drift.items():
        sev = str(entry.get("severity", "?"))
        buckets[sev].append(table)
    lines = [
        f"DRIFT SUMMARY: {len(drift)} tables across {len(buckets)} severity bucket(s).",
        "",
    ]
    # Sort by descending fix-priority.
    priority = ["critical", "business", "mixin", "stale_migration_column", "rename", "unloaded_model"]
    for sev in priority:
        tables = buckets.get(sev, [])
        if not tables:
            continue
        lines.append(f"  [{sev}] ({len(tables)} tables):")
        for t in sorted(tables):
            entry = drift[t]
            mo = entry.get("model_only") or []
            mo_n = len(mo) if isinstance(mo, list) else 0
            lines.append(f"    - {t} ({mo_n} model-only cols)")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _collect_migration_columns_via_alembic() -> dict[str, set[str]] | None:
    """Apply migrations to in-memory SQLite, then reflect resulting schema.

    Returns ``None`` if alembic upgrade fails (likely PG-specific DDL the
    SQLite dialect rejects); callers fall back to the AST-based parser.
    """
    import sqlalchemy as sa
    from sqlalchemy import inspect as sa_inspect

    tmp_db = Path(tempfile.gettempdir()) / "prt_drift_audit_alembic.db"
    if tmp_db.exists():
        tmp_db.unlink()

    # Point env.py at the audit DB instead of the bootstrap default.
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{tmp_db}"

    try:
        from alembic import command
        from alembic.config import Config
    except ImportError:
        return None

    cfg = Config(str(BACKEND_ROOT / "app" / "migrations" / "alembic.ini"))
    cfg.set_main_option(
        "script_location", str(BACKEND_ROOT / "app" / "migrations")
    )
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{tmp_db}")

    try:
        command.upgrade(cfg, "head")
    except Exception as exc:  # noqa: BLE001 — alembic raises many exception types
        print(f"alembic upgrade failed on SQLite: {exc!s}", file=sys.stderr)
        return None

    sync_engine = sa.create_engine(f"sqlite:///{tmp_db}")
    inspector = sa_inspect(sync_engine)
    schema: dict[str, set[str]] = {}
    for table_name in inspector.get_table_names():
        if table_name == "alembic_version":
            continue
        schema[table_name] = {c["name"] for c in inspector.get_columns(table_name)}
    return schema


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text.")
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Emit a per-severity rollup instead of the full table list.",
    )
    parser.add_argument(
        "--severity",
        choices=["critical", "business", "mixin", "rename", "unloaded_model", "stale_migration_column"],
        action="append",
        help=(
            "Filter output to one or more severity levels. Repeat the flag "
            "to combine (e.g. --severity critical --severity business)."
        ),
    )
    parser.add_argument(
        "--use-alembic",
        action="store_true",
        help=(
            "Apply migrations to in-memory SQLite via Alembic and diff the "
            "reflected schema (more accurate, requires alembic to succeed "
            "on SQLite). Falls back to AST parser if alembic fails."
        ),
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    _bootstrap_env()
    model_columns = _load_model_columns()
    migration_columns: dict[str, set[str]] | None = None
    if args.use_alembic:
        migration_columns = _collect_migration_columns_via_alembic()
        if migration_columns is None:
            print(
                "Alembic mode failed; falling back to AST parser.", file=sys.stderr
            )
    if migration_columns is None:
        migration_columns, _per_file = _collect_migration_columns()
    drift = _diff(model_columns, migration_columns)

    if args.severity:
        drift = {
            t: e for t, e in drift.items() if e.get("severity") in set(args.severity)
        }

    if args.json:
        print(json.dumps(drift, indent=2, sort_keys=True))
    elif args.summary:
        print(_format_summary(drift))
    else:
        print(_format_text(drift))

    # Exit non-zero only for severities that demand a fix (critical/business).
    # Mixin/rename/unloaded_model are informational unless the caller filters.
    actionable = {
        t for t, e in drift.items() if e.get("severity") in {"critical", "business"}
    }
    return 1 if actionable else 0


if __name__ == "__main__":
    sys.exit(main())
