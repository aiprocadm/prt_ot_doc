"""Lightweight column-level drift audit. Pure AST, no app imports.

Companion to ``version_column_drift.py`` (which is specialized for the
``version`` column from ``VersionedMixin``). This script answers the
broader question: **for every TenantBaseModel/SharedModel class, do all
its ``Mapped[...]`` columns appear in some migration?**

This bypasses the heavy ``check_orm_migration_drift.py`` path (which
hangs locally on Win+Py3.13 due to the ``app.db.base`` import chain —
confirmed via Session 80 reproduction).

Detection scope (mirrors ``version_column_drift.py`` v3):
  - Direct ``op.create_table("t", sa.Column("c", ...), ...)``.
  - Direct ``op.add_column("t", sa.Column("c", ...))``.
  - Helper-wrapped: ``_create_table("t", sa.Column("c", ...))`` where
    ``_create_table`` contains ``op.create_table(...)``. The helper's
    body is walked for ``sa.Column("<name>", ...)`` literals AND for
    same-module helper calls (handles ``_base_columns()`` indirection
    in ``20260317_next46_training_briefings_offline.py``).
  - Loop variables: ``for t in _TABLES: op.add_column(t, sa.Column("c", ...))``
    where ``_TABLES`` is a module-level constant string sequence
    (the v3 mechanism — credits all values in the sequence).
  - Dynamic batch_alter_table (iter-39):
    ``t = _resolve(...); with op.batch_alter_table(t, ...): batch.add_column(...)``
    where ``_resolve`` is a same-module function with one or more
    ``return "<literal>"`` statements. Cols credit to ALL possible
    return-literal table names. Closes false-positive on ``npabinding``
    in ``8d2c1a6c5e24_domain_normalization.py``.

Mixin awareness: a fixed set of column names provided by base mixins
(``TenantBaseModel``, ``SoftDeleteMixin``, etc.) is subtracted from each
model's column set before comparison. This avoids false positives for
``id``, ``tenant_id``, ``created_at``, etc., which migrations get via
``_base_columns()``-style helpers.

Usage:
    py -3 scripts/audit/column_drift_lite.py            # all tables
    py -3 scripts/audit/column_drift_lite.py --verbose  # show per-table diff
    py -3 scripts/audit/column_drift_lite.py --table training_enrollments  # single
"""

from __future__ import annotations

import argparse
import ast
import sys
from collections import defaultdict
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
MODELS_DIR = REPO_ROOT / "backend" / "app" / "models"
# iter-44 multi-file scope: scan all ``backend/app/models/*.py``, not just
# ``models.py``. Closes the 5th audit static-analysis blindspot (single-file
# scope). Excluded by filename: ``__init__.py`` (re-export only by convention),
# ``base.py`` (mixin/base classes whose bases don't match VERSIONED_BASES).
_MODELS_SKIP_FILES = frozenset({"__init__.py", "base.py"})
BASE_FILE = MODELS_DIR / "base.py"
MIGRATIONS_DIR = REPO_ROOT / "backend" / "app" / "migrations" / "versions"

VERSIONED_BASES = {"TenantBaseModel", "SharedModel"}
# Columns provided by base mixins. If a model inherits a mixin that adds
# these, the migration's _base_columns() helper provides them too — so we
# don't expect direct create_table arg matches.
MIXIN_COLUMNS = frozenset(
    {
        "id",
        "tenant_id",
        "created_at",
        "updated_at",
        "version",
        "deleted_at",
        "is_deleted",
    }
)


# ---------------------------------------------------------------------------
# Generic AST helpers (mirrors version_column_drift.py).
# ---------------------------------------------------------------------------


def _all_functions(tree: ast.Module) -> dict[str, ast.FunctionDef]:
    return {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}


def _table_creating_helpers(functions: dict[str, ast.FunctionDef]) -> set[str]:
    helpers: set[str] = set()
    for name, func in functions.items():
        if name in ("upgrade", "downgrade"):
            continue
        for inner in ast.walk(func):
            if (
                isinstance(inner, ast.Call)
                and isinstance(inner.func, ast.Attribute)
                and inner.func.attr == "create_table"
            ):
                helpers.add(name)
                break
    return helpers


def _module_string_seqs(tree: ast.Module) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}

    def _extract(value: ast.expr | None) -> list[str] | None:
        if not isinstance(value, (ast.Tuple, ast.List)):
            return None
        values: list[str] = []
        for elt in value.elts:
            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                values.append(elt.value)
            else:
                return None
        return values

    for node in tree.body:
        if isinstance(node, ast.Assign):
            extracted = _extract(node.value)
            if extracted is None:
                continue
            for target in node.targets:
                if isinstance(target, ast.Name):
                    result[target.id] = extracted
        elif isinstance(node, ast.AnnAssign):
            if not isinstance(node.target, ast.Name):
                continue
            extracted = _extract(node.value)
            if extracted is not None:
                result[node.target.id] = extracted
    return result


def _resolve_iter(iter_node: ast.expr, module_constants: dict[str, list[str]]) -> list[str] | None:
    if isinstance(iter_node, (ast.Tuple, ast.List)):
        values: list[str] = []
        for elt in iter_node.elts:
            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                values.append(elt.value)
            else:
                return None
        return values
    if isinstance(iter_node, ast.Name):
        seq = module_constants.get(iter_node.id)
        return list(seq) if seq is not None else None
    return None


def _parent_map(root: ast.AST) -> dict[int, ast.AST]:
    parents: dict[int, ast.AST] = {}
    for node in ast.walk(root):
        for child in ast.iter_child_nodes(node):
            parents[id(child)] = node
    return parents


def _enclosing_for_bindings(
    node: ast.AST,
    parents: dict[int, ast.AST],
    module_constants: dict[str, list[str]],
) -> dict[str, list[str]]:
    bindings: dict[str, list[str]] = {}
    cur = parents.get(id(node))
    while cur is not None:
        if (
            isinstance(cur, ast.For)
            and isinstance(cur.target, ast.Name)
            and cur.target.id not in bindings
        ):
            values = _resolve_iter(cur.iter, module_constants)
            if values is not None:
                bindings[cur.target.id] = values
        cur = parents.get(id(cur))
    return bindings


def _column_name(call: ast.Call) -> str | None:
    """If ``call`` is ``sa.Column("name", ...)`` or ``Column("name", ...)``,
    return ``"name"``; otherwise ``None``."""
    func = call.func
    is_col = (
        (isinstance(func, ast.Attribute) and func.attr == "Column")
        or (isinstance(func, ast.Name) and func.id == "Column")
    )
    if not is_col or not call.args:
        return None
    first = call.args[0]
    if isinstance(first, ast.Constant) and isinstance(first.value, str):
        return first.value
    return None


# ---------------------------------------------------------------------------
# Model-side: extract Mapped[...] columns from each versioned class.
# ---------------------------------------------------------------------------


def _is_mapped_annotation(annotation: ast.expr | None) -> bool:
    """True if annotation is ``Mapped[...]`` (with or without subscript)."""
    if annotation is None:
        return False
    if isinstance(annotation, ast.Subscript):
        if isinstance(annotation.value, ast.Name) and annotation.value.id == "Mapped":
            return True
    if isinstance(annotation, ast.Name) and annotation.id == "Mapped":
        return True
    return False


def _is_column_value(value: ast.expr | None) -> bool:
    """True if the AnnAssign value is ``mapped_column(...)`` or ``Column(...)``.

    Rejects ``relationship(...)`` and other non-column factories — those are
    ORM-level joins, not DDL columns, and shouldn't be expected in migrations.
    """
    if not isinstance(value, ast.Call):
        return False
    func = value.func
    if isinstance(func, ast.Name):
        return func.id in ("mapped_column", "Column")
    if isinstance(func, ast.Attribute):
        return func.attr in ("mapped_column", "Column")
    return False


class ModelInfo:
    __slots__ = ("class_name", "tablename", "columns", "bases")

    def __init__(self, class_name: str, tablename: str, columns: set[str], bases: set[str]) -> None:
        self.class_name = class_name
        self.tablename = tablename
        self.columns = columns
        self.bases = bases

    def __repr__(self) -> str:
        return f"ModelInfo({self.class_name}, {self.tablename}, {len(self.columns)} cols)"


def _discover_model_files() -> list[Path]:
    """Return all ``MODELS_DIR/*.py`` files worth scanning.

    Excludes ``__init__.py`` (re-export-only by convention) and ``base.py``
    (mixin/base classes whose bases don't match ``VERSIONED_BASES`` anyway).
    Sorted for deterministic iteration order.
    """
    return sorted(
        p for p in MODELS_DIR.glob("*.py") if p.name not in _MODELS_SKIP_FILES
    )


def _versioned_models_in_tree(tree: ast.Module) -> dict[str, ModelInfo]:
    """Extract ``{tablename: ModelInfo}`` from a single parsed module tree."""
    result: dict[str, ModelInfo] = {}
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        bases = {b.id for b in node.bases if isinstance(b, ast.Name)}
        if not (bases & VERSIONED_BASES):
            continue
        tablename = node.name.lower()
        columns: set[str] = set()
        for sub in node.body:
            if (
                isinstance(sub, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == "__tablename__" for t in sub.targets)
                and isinstance(sub.value, ast.Constant)
                and isinstance(sub.value.value, str)
            ):
                tablename = sub.value.value
            elif isinstance(sub, ast.AnnAssign) and isinstance(sub.target, ast.Name):
                # Mapped[T] = mapped_column(...) → column; relationship(...) → skip.
                if _is_mapped_annotation(sub.annotation) and _is_column_value(sub.value):
                    # SQLAlchemy: ``mapped_column("db_name", ...)`` overrides
                    # the Python attribute name as the DB column name (the
                    # first positional arg, when it's a string Constant).
                    # Otherwise the attribute name is the column name.
                    db_name = sub.target.id
                    if isinstance(sub.value, ast.Call) and sub.value.args:
                        first = sub.value.args[0]
                        if isinstance(first, ast.Constant) and isinstance(first.value, str):
                            db_name = first.value
                    columns.add(db_name)
        result[tablename] = ModelInfo(node.name, tablename, columns, bases)
    return result


def find_versioned_models() -> dict[str, ModelInfo]:
    """Map ``{tablename: ModelInfo}`` for every class inheriting one of
    ``VERSIONED_BASES`` either directly or transitively (e.g. via
    ``SoftDeleteMixin``).

    iter-44: walks every ``*.py`` in ``MODELS_DIR`` (excluding ``__init__.py``
    and ``base.py``), not just ``models.py``. Closes the 5th audit
    static-analysis blindspot from Session 93 — model classes in
    ``approval_workflow.py``, ``job_engine.py``, ``risk.py``, etc. are now
    visible to the audit.
    """
    result: dict[str, ModelInfo] = {}
    for path in _discover_model_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for tablename, info in _versioned_models_in_tree(tree).items():
            # Later files don't silently replace earlier ones (would mask
            # legitimate duplicate __tablename__ declarations).
            result.setdefault(tablename, info)
    return result


# ---------------------------------------------------------------------------
# Migration-side: extract per-table column sets.
# ---------------------------------------------------------------------------


def _helper_injected_columns(
    functions: dict[str, ast.FunctionDef], helper_name: str
) -> set[str]:
    """All column names a helper transitively injects.

    Walks helper body for ``sa.Column("<name>", ...)`` literals and recurses
    into other same-module helpers called from the body.
    """
    injected: set[str] = set()
    visited: set[str] = set()

    def _walk(name: str) -> None:
        if name in visited:
            return
        visited.add(name)
        func = functions.get(name)
        if func is None:
            return
        for node in ast.walk(func):
            if not isinstance(node, ast.Call):
                continue
            col = _column_name(node)
            if col is not None:
                injected.add(col)
                continue
            # Recurse into other module-local helpers.
            f = node.func
            if isinstance(f, ast.Name) and f.id in functions and f.id != name:
                _walk(f.id)

    _walk(helper_name)
    return injected


def _columns_in_create_table_call(call: ast.Call) -> set[str]:
    """Column names from ``op.create_table("t", sa.Column("c", ...), ...)``."""
    cols: set[str] = set()
    for arg in call.args[1:]:
        if isinstance(arg, ast.Call):
            col = _column_name(arg)
            if col is not None:
                cols.add(col)
    return cols


def _extract_alter_rename_kwarg(call: ast.Call) -> str | None:
    """If ``call`` includes ``new_column_name="X"`` kwarg, return ``"X"``."""
    for kw in call.keywords:
        if kw.arg == "new_column_name":
            if isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                return kw.value.value
    return None


def _function_return_literals(func: ast.FunctionDef) -> set[str]:
    """All string literals returned by ``func``. Ignores ``return None`` and
    non-Constant-str returns. Used by dynamic batch_alter_table resolution
    (iter-39) to find which table names a resolver function can produce.
    """
    literals: set[str] = set()
    for node in ast.walk(func):
        if isinstance(node, ast.Return):
            if (
                isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)
            ):
                literals.add(node.value.value)
    return literals


def _resolve_dynamic_name_from_assignments(
    var_name: str,
    scope_fn: ast.FunctionDef,
    functions: dict[str, ast.FunctionDef],
) -> list[str]:
    """Resolve ``var_name`` to possible string-literal values by tracing
    assignments inside ``scope_fn``.

    For each ``Assign`` where ``var_name`` is a target and the RHS is
    a ``Call`` to a same-module function (in ``functions``), collect
    the callee's string-literal returns. Returns a sorted list (for
    deterministic test assertions). Empty list when no traceable
    assignment is found — caller should treat that as "skip block".

    Real-world pattern (``8d2c1a6c5e24_domain_normalization.py:269``):
        npa_binding_table = _resolve_npa_binding_table(bind)
        if npa_binding_table:
            with op.batch_alter_table(npa_binding_table, schema=None) as b:
                b.add_column(sa.Column("entity_type", ...))
    """
    literals: set[str] = set()
    for node in ast.walk(scope_fn):
        if not isinstance(node, ast.Assign):
            continue
        if not any(
            isinstance(t, ast.Name) and t.id == var_name for t in node.targets
        ):
            continue
        if not isinstance(node.value, ast.Call):
            continue
        called = node.value.func
        if isinstance(called, ast.Name) and called.id in functions:
            literals |= _function_return_literals(functions[called.id])
    return sorted(literals)


def collect_migration_columns(verbose: bool = False) -> dict[str, set[str]]:
    """Return ``{tablename: set_of_columns}`` across all migrations.

    Tracks add (create_table + add_column + helper-wrapped + loop variants),
    drop (drop_column + batch.drop_column), and rename (alter_column with
    ``new_column_name=``). Renames apply within a single migration's pass;
    drops remove columns from the cumulative per-table set.

    Applies table renames so the latest table name picks up history from
    the pre-rename name.
    """
    per_table: dict[str, set[str]] = defaultdict(set)
    renames: dict[str, str] = {}

    for mig_path in sorted(MIGRATIONS_DIR.glob("*.py")):
        if mig_path.name.startswith("__"):
            continue
        try:
            src = mig_path.read_text(encoding="utf-8")
            tree = ast.parse(src, filename=str(mig_path))
        except (UnicodeDecodeError, SyntaxError) as exc:
            print(f"WARN: skipping {mig_path.name}: {exc}", file=sys.stderr)
            continue
        upgrade_fn = None
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name == "upgrade":
                upgrade_fn = node
                break
        if upgrade_fn is None:
            continue
        functions = _all_functions(tree)
        helpers = _table_creating_helpers(functions)
        helper_cols_map = {h: _helper_injected_columns(functions, h) for h in helpers}
        module_constants = _module_string_seqs(tree)
        parents = _parent_map(upgrade_fn)

        for node in ast.walk(upgrade_fn):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            # ---- Direct op.create_table("t", sa.Column("c", ...), ...) ----
            is_create = (
                (isinstance(func, ast.Attribute) and func.attr == "create_table")
                or (isinstance(func, ast.Name) and func.id == "create_table")
            )
            if is_create and node.args:
                first = node.args[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    per_table[first.value].update(_columns_in_create_table_call(node))
            # ---- Helper-wrapped: <helper>("t", sa.Column("c", ...), ...) ----
            if (
                isinstance(func, ast.Name)
                and func.id in helpers
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                tname = node.args[0].value
                # Explicit columns passed to the helper.
                for arg in node.args[1:]:
                    if isinstance(arg, ast.Call):
                        col = _column_name(arg)
                        if col is not None:
                            per_table[tname].add(col)
                # Columns the helper injects (e.g. _base_columns()).
                per_table[tname].update(helper_cols_map.get(func.id, set()))
            # ---- Direct op.add_column("t", sa.Column("c", ...)) ----
            is_add = (
                (isinstance(func, ast.Attribute) and func.attr == "add_column")
                or (isinstance(func, ast.Name) and func.id == "add_column")
            )
            if is_add and len(node.args) >= 2:
                col_arg = node.args[1]
                if isinstance(col_arg, ast.Call):
                    col = _column_name(col_arg)
                    if col is not None:
                        tname_arg = node.args[0]
                        candidates: list[str] = []
                        if isinstance(tname_arg, ast.Constant) and isinstance(tname_arg.value, str):
                            candidates = [tname_arg.value]
                        elif isinstance(tname_arg, ast.Name):
                            bindings = _enclosing_for_bindings(node, parents, module_constants)
                            candidates = bindings.get(tname_arg.id, [])
                        for tn in candidates:
                            per_table[tn].add(col)
            # ---- op.rename_table("old", "new") ----
            is_rename = (
                (isinstance(func, ast.Attribute) and func.attr == "rename_table")
                or (isinstance(func, ast.Name) and func.id == "rename_table")
            )
            if is_rename and len(node.args) >= 2:
                a, b = node.args[0], node.args[1]
                if (
                    isinstance(a, ast.Constant) and isinstance(a.value, str)
                    and isinstance(b, ast.Constant) and isinstance(b.value, str)
                ):
                    renames[a.value] = b.value

        # Direct op.drop_column("t", "col") — subtract from cumulative set.
        for node in ast.walk(upgrade_fn):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            is_drop = (
                (isinstance(func, ast.Attribute) and func.attr == "drop_column")
                or (isinstance(func, ast.Name) and func.id == "drop_column")
            )
            if not is_drop or len(node.args) < 2:
                continue
            tname_arg, col_arg = node.args[0], node.args[1]
            if (
                isinstance(tname_arg, ast.Constant)
                and isinstance(tname_arg.value, str)
                and isinstance(col_arg, ast.Constant)
                and isinstance(col_arg.value, str)
            ):
                per_table[tname_arg.value].discard(col_arg.value)

        # Direct op.alter_column("t", "old", new_column_name="new") — rename.
        for node in ast.walk(upgrade_fn):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            is_alter = (
                (isinstance(func, ast.Attribute) and func.attr == "alter_column")
                or (isinstance(func, ast.Name) and func.id == "alter_column")
            )
            if not is_alter or len(node.args) < 2:
                continue
            tname_arg, col_arg = node.args[0], node.args[1]
            if not (
                isinstance(tname_arg, ast.Constant) and isinstance(tname_arg.value, str)
                and isinstance(col_arg, ast.Constant) and isinstance(col_arg.value, str)
            ):
                continue
            new_name = _extract_alter_rename_kwarg(node)
            if new_name is not None:
                tname = tname_arg.value
                per_table[tname].discard(col_arg.value)
                per_table[tname].add(new_name)

        # batch_alter_table — handle batch.add_column / batch.drop_column / batch.alter_column inside.
        # iter-39: also resolves dynamic table name when ctx.args[0] is a
        # `Name` bound to a same-module function returning string literals.
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
                ):
                    continue
                first = ctx.args[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    tnames: list[str] = [first.value]
                elif isinstance(first, ast.Name):
                    tnames = _resolve_dynamic_name_from_assignments(
                        first.id, upgrade_fn, functions
                    )
                    if not tnames:
                        continue
                else:
                    continue
                for inner in ast.walk(node):
                    if not isinstance(inner, ast.Call):
                        continue
                    f = inner.func
                    if not isinstance(f, ast.Attribute):
                        continue
                    # batch.add_column(sa.Column("col", ...))
                    if f.attr == "add_column" and inner.args and isinstance(inner.args[0], ast.Call):
                        col = _column_name(inner.args[0])
                        if col is not None:
                            for tn in tnames:
                                per_table[tn].add(col)
                    # batch.drop_column("col")
                    elif (
                        f.attr == "drop_column"
                        and inner.args
                        and isinstance(inner.args[0], ast.Constant)
                        and isinstance(inner.args[0].value, str)
                    ):
                        for tn in tnames:
                            per_table[tn].discard(inner.args[0].value)
                    # batch.alter_column("old", new_column_name="new")
                    elif (
                        f.attr == "alter_column"
                        and inner.args
                        and isinstance(inner.args[0], ast.Constant)
                        and isinstance(inner.args[0].value, str)
                    ):
                        new_name = _extract_alter_rename_kwarg(inner)
                        if new_name is not None:
                            for tn in tnames:
                                per_table[tn].discard(inner.args[0].value)
                                per_table[tn].add(new_name)

    # Apply renames: new table inherits old table's history.
    for old, new in renames.items():
        if old in per_table:
            per_table[new] |= per_table[old]

    if verbose:
        sample = sorted(per_table.items())[:5]
        print(f"[verbose] migrations scanned; sample of first 5 tables:")
        for t, cols in sample:
            print(f"  {t}: {len(cols)} cols")

    return dict(per_table)


# ---------------------------------------------------------------------------
# Report.
# ---------------------------------------------------------------------------


def compute_drift(
    models: dict[str, ModelInfo],
    migration_cols: dict[str, set[str]],
) -> list[tuple[ModelInfo, set[str]]]:
    """For each model, return columns declared on the model but missing from migrations.

    Mixin columns are excluded from both sides automatically.
    """
    drift: list[tuple[ModelInfo, set[str]]] = []
    for tn, info in sorted(models.items()):
        mig = migration_cols.get(tn, set())
        # Subtract mixin columns from BOTH sides — if a mixin col is in the
        # model but not directly in migration (because _base_columns injects
        # it without us decoding the helper), we don't want false drift.
        model_business = info.columns - MIXIN_COLUMNS
        mig_business = mig - MIXIN_COLUMNS
        missing = model_business - mig_business
        if missing:
            drift.append((info, missing))
    return drift


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--table", help="restrict to one table")
    parser.add_argument("--verbose", action="store_true", help="extra diagnostic output")
    args = parser.parse_args()

    models = find_versioned_models()
    migration_cols = collect_migration_columns(verbose=args.verbose)

    if args.table:
        if args.table not in models:
            print(f"Table {args.table!r} not found among versioned model tables.", file=sys.stderr)
            return 2
        info = models[args.table]
        mig = migration_cols.get(args.table, set())
        model_business = info.columns - MIXIN_COLUMNS
        mig_business = mig - MIXIN_COLUMNS
        print(f"== {args.table} ({info.class_name}) ==")
        print(f"  bases: {sorted(info.bases)}")
        print(f"  model cols ({len(info.columns)}): {sorted(info.columns)}")
        print(f"  migration cols ({len(mig)}): {sorted(mig)}")
        print(f"  model_business - migration_business: {sorted(model_business - mig_business) or '(none)'}")
        print(f"  migration_business - model_business: {sorted(mig_business - model_business) or '(none)'}")
        return 0

    drift = compute_drift(models, migration_cols)
    absent = [info for info in models.values() if info.tablename not in migration_cols]
    print(f"Versioned model classes scanned: {len(models)}")
    print(f"Migrations columns indexed for: {len(migration_cols)} tables")
    print()
    print(f"=== BUSINESS-DRIFT (model cols missing in migrations): {len(drift)} tables ===")
    for info, missing in drift:
        print(f"  {info.tablename}  ({info.class_name})  missing: {sorted(missing)}")
    print()
    print(f"=== TABLES ABSENT FROM MIGRATIONS (critical): {len(absent)} ===")
    for info in sorted(absent, key=lambda i: i.tablename):
        print(f"  {info.tablename}  ({info.class_name})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
