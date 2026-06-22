"""Pin-test (regression guard): Alembic migrations may only reference tables /
columns that are guaranteed to exist along their down-revision chain.

Background
==========
The alembic graph in this repo has 11+ parallel branches that merge only in
``20260416_next69_merge_heads.py``. A migration on branch A that does
``op.batch_alter_table("X")`` requires table ``X`` to exist; if ``X`` was
created on branch B and branch A doesn't list B in its ``down_revision`` /
``depends_on``, ``alembic upgrade head`` on a fresh DB picks an ordering where
``X`` is touched before being created → ``UndefinedTableError`` /
``UndefinedColumnError`` at upgrade time.

Iter-9 (PR #557) closed one such case point-wise
(``20250501_reliability_outbox_webhook_delivery`` → declared ``depends_on =
"20250322_add_webhook_subscriptions"``). Iter-10 introduces this DAG-level
analyzer to catch the rest of the class structurally and prevent regressions.

What this pin-test does
=======================
For each migration ``M`` in ``backend/app/migrations/versions``:

1. Parse ``revision``, ``down_revision`` (single str | tuple/list | None) and
   ``depends_on`` (same shape) via ``ast``.
2. Build the predecessor closure ``preds(M)`` — every revision reachable from
   ``M`` walking ``down_revision`` ∪ ``depends_on`` edges backwards.
3. Extract the **dependency set** of ``M``: every (table) or (table, column)
   that ``M``'s upgrade body references via structured Alembic API calls:
     - ``op.batch_alter_table("T")``
     - ``op.add_column("T", ...)``, ``batch.add_column(...)``
     - ``op.drop_column("T", ...)``, ``batch.drop_column(...)``
     - ``op.alter_column("T", ...)``, ``batch.alter_column(...)``
     - ``op.create_index(..., "T", [cols])``, ``batch.create_index(..., [cols])``
     - ``op.create_foreign_key(..., "src", "ref", [src_cols], [ref_cols])``
     - ``op.create_unique_constraint(..., "T", [cols])``,
       ``batch.create_unique_constraint(..., [cols])``
     - ``op.drop_table("T")``, ``op.rename_table("old", ...)``
   Raw ``op.execute("SQL")`` is intentionally out of scope — too unstructured.
4. Extract the **creates set** of ``M``:
     - ``op.create_table("T", sa.Column("a", ...), ...)`` → creates table T and
       every column in T.
     - ``op.add_column("T", sa.Column("a", ...))``, ``batch.add_column(...)``
       → creates column ``a`` on T.
5. For every dep ``d`` in ``M``'s dependency set: confirm there exists some
   ``M'`` in ``preds(M) ∪ {M}`` whose creates-set contains ``d``. Otherwise
   ``d`` is a **violation** — either cross-branch dep or missing migration.

What this pin-test does NOT do
==============================
- Detect intra-migration ordering bugs (``alter`` before ``create_table`` in
  the same file). These tend to fail at the very first ``alembic upgrade head``
  on any backend and are not the regression class we're guarding here.
- Parse raw SQL in ``op.execute(...)``. Conservative: false negatives
  acceptable, false positives are not.
- Detect column type mismatches or constraint-shape drift.

History
-------
* iter-7..iter-9: class-1 (enum double-create) and class-3 (uncreated enum in
  add_column) pinned in ``tests/test_migrations_enum_create_type_safety.py``.
* iter-9 (commit ``ab0679c``): one targeted ``depends_on`` fix for class-2
  cross-branch table dep (20250501 → 20250322). Pin-test deferred to iter-10.
* iter-10 (this file): DAG-level analyzer for class-2 / class-4 / missing
  migrations.

Running locally without pytest (Windows+Py3.13 conftest hang workaround)
------------------------------------------------------------------------
    python tests/test_migrations_cross_branch_deps.py

Exits 0 on no violations, 1 with a printed list otherwise.
"""

from __future__ import annotations

import ast
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS_DIR = REPO_ROOT / "backend" / "app" / "migrations" / "versions"

# Tables managed by Alembic itself (not by any migration). The version table is
# created by ``alembic upgrade`` before applying revisions, so referencing it
# from a migration is always safe.
ALEMBIC_INTERNAL_TABLES: frozenset[str] = frozenset({"alembic_version"})

# Migrations whose specific table references are intentionally guarded by an
# explicit runtime check (e.g., ``SELECT to_regclass('public.X') IS NOT NULL``
# → ``if X_exists: ...``). These references will not raise on a fresh DB and
# do not need a ``depends_on`` edge. Keys are revision ids; values are sets of
# table names allow-listed for that revision specifically.
#
# Each entry must include a one-line justification in a code comment. Do NOT
# extend this set without a paired comment — that is the whole point of the
# pin-test.
RUNTIME_GUARDED_TABLE_REFS: dict[str, frozenset[str]] = {
    # 4a45e0c64b41 (2024-02-29) is a legacy migration that conditionally edits
    # the old singular ``ppe_norm`` table only when ``to_regclass('public.
    # ppe_norm') IS NOT NULL`` returns true. On a fresh DB this is false and
    # the whole block is skipped. The current (post-20260401) schema uses
    # ``ppe_norms`` (plural); this guard exists for legacy data carry-over.
    "4a45e0c64b41": frozenset({"ppe_norm"}),
}


# ---------------------------------------------------------------------------
# Data shapes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Violation:
    """A single dependency from one migration that no predecessor creates."""

    migration: str  # revision id of the migration that has the bad ref
    file: str  # repo-relative path
    table: str
    column: str | None  # None → table-level dep, str → column-level dep
    why: str  # one-line explanation


@dataclass
class Migration:
    revision: str
    path: Path
    down_revision: tuple[str, ...]  # () for the root migration
    depends_on: tuple[str, ...]
    creates_tables: set[str] = field(default_factory=set)
    # (table, column) pairs created here (incl. cols added by create_table)
    creates_columns: set[tuple[str, str]] = field(default_factory=set)
    # tables this migration references via Alembic ops
    refs_tables: set[str] = field(default_factory=set)
    # (table, column) pairs referenced by name in alter/index/fk/uq ops
    refs_columns: set[tuple[str, str]] = field(default_factory=set)
    # (old, new) table-rename edges declared in this migration's upgrade body
    rename_edges: list[tuple[str, str]] = field(default_factory=list)
    # (table, old_col, new_col) column renames inside batch_alter_table
    column_rename_edges: list[tuple[str, str, str]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------


def _str_const(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _str_kwarg(call: ast.Call, name: str) -> str | None:
    """Return the string-constant value of keyword argument ``name``, or None."""
    for kw in call.keywords:
        if kw.arg == name:
            return _str_const(kw.value)
    return None


def _none_const(node: ast.AST | None) -> bool:
    return isinstance(node, ast.Constant) and node.value is None


def _str_tuple(node: ast.AST | None) -> tuple[str, ...]:
    """Extract a tuple of string constants from a literal tuple/list AST node.

    Returns () for None, a single string, or anything that isn't a plain
    literal of strings. (Non-literal forms — e.g. a variable reference — are
    rare in Alembic revision metadata; if they appear, this analyzer treats
    them conservatively as "no edge", which may produce false positives the
    operator must resolve manually.)
    """
    if node is None or _none_const(node):
        return ()
    s = _str_const(node)
    if s is not None:
        return (s,)
    if isinstance(node, (ast.Tuple, ast.List)):
        out: list[str] = []
        for elt in node.elts:
            v = _str_const(elt)
            if v is not None:
                out.append(v)
        return tuple(out)
    return ()


def _module_assigns(tree: ast.Module) -> dict[str, ast.AST]:
    """Return module-level Assign target name → value AST node."""
    out: dict[str, ast.AST] = {}
    for node in tree.body:
        # `revision = "..."`
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    out[target.id] = node.value
        # `revision: str = "..."`
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.value is not None:
                out[node.target.id] = node.value
    return out


def _func_node(tree: ast.Module, name: str) -> ast.FunctionDef | None:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    return None


def _is_attr_call(call: ast.Call, owner: str | None, attr: str) -> bool:
    """True if call is ``<owner>.<attr>(...)``. If owner is None, owner-name is
    not constrained (matches any ``X.attr(...)``)."""
    func = call.func
    if not isinstance(func, ast.Attribute) or func.attr != attr:
        return False
    if owner is None:
        return True
    return isinstance(func.value, ast.Name) and func.value.id == owner


def _is_op_call(call: ast.Call, attr: str) -> bool:
    return _is_attr_call(call, "op", attr)


def _is_sa_column(call: ast.Call) -> bool:
    """True for ``sa.Column(...)`` or bare ``Column(...)`` (rarer)."""
    func = call.func
    if isinstance(func, ast.Attribute) and func.attr == "Column":
        return isinstance(func.value, ast.Name) and func.value.id == "sa"
    if isinstance(func, ast.Name) and func.id == "Column":
        return True
    return False


def _column_names_from_call_args(call: ast.Call) -> list[str]:
    """Collect every ``sa.Column("name", ...)`` first-arg name in the
    arguments of ``call`` (including columns nested one level deep inside
    list/tuple literals — covers e.g. ``op.create_table("t", [Column("a"), Column("b")])``)."""
    out: list[str] = []
    for arg in call.args:
        if isinstance(arg, ast.Call) and _is_sa_column(arg) and arg.args:
            name = _str_const(arg.args[0])
            if name:
                out.append(name)
        elif isinstance(arg, (ast.List, ast.Tuple)):
            for elt in arg.elts:
                if isinstance(elt, ast.Call) and _is_sa_column(elt) and elt.args:
                    name = _str_const(elt.args[0])
                    if name:
                        out.append(name)
    return out


def _is_batch_call(call: ast.Call, attr: str) -> bool:
    """True for ``<anything>.attr(...)`` where ``<anything>`` is a Name. Used
    for batch operations where the batch variable name varies (``batch``,
    ``bop``, ``b``, ...)."""
    func = call.func
    if not isinstance(func, ast.Attribute) or func.attr != attr:
        return False
    # We rely on with-statement context to bind table; here we just need to
    # know "is this a batch-style call". Accept Name or Attribute owners.
    return isinstance(func.value, (ast.Name, ast.Attribute))


def _column_names_from_list(node: ast.AST | None) -> list[str]:
    """For nodes like ``["a", "b"]`` or ``("a", "b")`` return ['a', 'b'].
    Non-literal forms (a variable) → []."""
    if not isinstance(node, (ast.List, ast.Tuple)):
        return []
    out: list[str] = []
    for elt in node.elts:
        s = _str_const(elt)
        if s is not None:
            out.append(s)
    return out


def _column_names_from_create_table(
    call: ast.Call, column_helpers: dict[str, list[str]] | None = None
) -> list[str]:
    """Pull column names out of ``op.create_table("t", sa.Column("a", ...), ...)``.

    First positional arg is the table name; subsequent positional args are
    column / constraint declarations. Handles three forms:

      1. inline literal: ``sa.Column("name", ...)``
      2. starred call to a known column-returning helper: ``*_base_cols()``
         — inlined via the ``column_helpers`` map (function name → column list)
      3. starred name reference: ``*some_var`` — skipped (would require dataflow)
    """
    helpers = column_helpers or {}
    cols: list[str] = []
    for arg in call.args[1:]:
        # Form 2: *helper_call() / *helper_call(args)
        if isinstance(arg, ast.Starred) and isinstance(arg.value, ast.Call):
            target_call = arg.value
            tfunc = target_call.func
            if isinstance(tfunc, ast.Name) and tfunc.id in helpers:
                cols.extend(helpers[tfunc.id])
            continue
        # Form 1: sa.Column("name", ...) / Column(...)
        if isinstance(arg, ast.Call) and _is_sa_column(arg) and arg.args:
            name = _str_const(arg.args[0])
            if name:
                cols.append(name)
    return cols


def _column_name_from_add_column(call: ast.Call) -> str | None:
    """For ``op.add_column("t", sa.Column("c", ...))`` (or batch.add_column)
    return ``c``. The Column() is in args[1] for op.add_column, args[0] for
    batch.add_column."""
    # Search both positions — caller may invoke with either shape.
    for arg in call.args:
        if isinstance(arg, ast.Call):
            func = arg.func
            is_col = (
                isinstance(func, ast.Attribute)
                and func.attr == "Column"
                and isinstance(func.value, ast.Name)
                and func.value.id == "sa"
            ) or (isinstance(func, ast.Name) and func.id == "Column")
            if is_col and arg.args:
                name = _str_const(arg.args[0])
                if name:
                    return name
    return None


# ---------------------------------------------------------------------------
# Module-level helper analysis (one-time per migration file)
# ---------------------------------------------------------------------------
#
# Many migrations factor table-creation through local wrappers
# (``_create_table``, ``_create_soft_table``) and column-list helpers
# (``_base_columns`` returning a list of ``sa.Column`` literals). Without
# inlining these, the analyzer reports false-positive "table/column never
# created" violations.
#
# The detection is intentionally conservative: a helper qualifies only if its
# first positional parameter flows directly into ``op.create_table`` as the
# table-name argument. Anything more dynamic (computed table names, kwargs-
# driven dispatch) is not recognized.


def _collect_column_helpers(tree: ast.Module) -> dict[str, list[str]]:
    """Map ``def helper(...) -> list[sa.Column]: ...`` → list of every column
    name declared anywhere in the helper body via ``sa.Column("name", ...)``.

    We deliberately ignore conditional shape (``if flag: cols.insert(...)``) and
    return the union of all literal columns. For a pin-test, **over**-recording
    creates is safe: it can only cause false-negatives at the audit step (a
    real bug slipping through), not false-positives. A real bug here would
    have to involve a helper declaring a literal ``sa.Column("X")`` it never
    actually returns — vanishingly rare in this codebase.
    """
    out: dict[str, list[str]] = {}
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        cols: list[str] = []
        seen: set[str] = set()
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call) and _is_sa_column(sub) and sub.args:
                name = _str_const(sub.args[0])
                if name and name not in seen:
                    seen.add(name)
                    cols.append(name)
        if cols:
            out[node.name] = cols
    return out


def _collect_table_helpers(
    tree: ast.Module, column_helpers: dict[str, list[str]]
) -> dict[str, set[str]]:
    """Identify module-level functions that create a table from their first
    positional arg. For each, return the set of column names the helper itself
    contributes (collected from sa.Column literals in the helper body + any
    nested helper-call expansion against ``column_helpers``).

    A function qualifies as a table-helper iff its body contains a call
    ``op.create_table(<first-param-name>, ...)``.
    """
    helpers: dict[str, set[str]] = {}
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef) or not node.args.args:
            continue
        first_param = node.args.args[0].arg
        creates_table = False
        contributed: set[str] = set()
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call):
                if _is_op_call(sub, "create_table") and sub.args:
                    first_arg = sub.args[0]
                    if isinstance(first_arg, ast.Name) and first_arg.id == first_param:
                        creates_table = True
                        for col in _column_names_from_call_args(sub):
                            contributed.add(col)
                        # Walk Starred args for nested helper-call expansion
                        # when the helper composes args inline.
                        for arg in sub.args[1:]:
                            target_call: ast.Call | None = None
                            if isinstance(arg, ast.Starred) and isinstance(arg.value, ast.Call):
                                target_call = arg.value
                            elif isinstance(arg, ast.Call):
                                target_call = arg
                            if target_call is None:
                                continue
                            tfunc = target_call.func
                            if isinstance(tfunc, ast.Name) and tfunc.id in column_helpers:
                                contributed.update(column_helpers[tfunc.id])
                # Any column-helper call anywhere in the body contributes:
                # callers often pre-build ``args = list(cols) + _base_cols()``
                # outside the create_table call, then splat ``*args``.
                elif isinstance(sub.func, ast.Name) and sub.func.id in column_helpers:
                    contributed.update(column_helpers[sub.func.id])
                # Also collect helper-internal column declarations outside
                # op.create_table — rare but cheap to include.
                elif _is_sa_column(sub) and sub.args:
                    name = _str_const(sub.args[0])
                    if name:
                        contributed.add(name)
        if creates_table:
            helpers[node.name] = contributed
    return helpers


# ---------------------------------------------------------------------------
# Per-migration extraction
# ---------------------------------------------------------------------------


def _parse_revision_metadata(
    tree: ast.Module,
) -> tuple[str | None, tuple[str, ...], tuple[str, ...]]:
    """Return (revision_id, down_revisions, depends_on)."""
    assigns = _module_assigns(tree)
    rev = _str_const(assigns.get("revision"))
    down = _str_tuple(assigns.get("down_revision"))
    deps = _str_tuple(assigns.get("depends_on"))
    return rev, down, deps


def _walk_upgrade(tree: ast.Module) -> Iterable[tuple[ast.AST, str | None]]:
    """Yield (node, batch_table) for every AST node inside ``upgrade()``.

    ``batch_table`` is the table name bound by the enclosing
    ``with op.batch_alter_table("X") as batch:`` block, or None if the node
    is not inside such a block.
    """
    func = _func_node(tree, "upgrade")
    if func is None:
        return

    def walk(nodes: Iterable[ast.AST], batch_table: str | None):
        for n in nodes:
            if isinstance(n, ast.With):
                # Detect: with op.batch_alter_table("X") as batch
                inner_batch_table = batch_table
                for item in n.items:
                    ctx = item.context_expr
                    if isinstance(ctx, ast.Call) and _is_op_call(ctx, "batch_alter_table"):
                        if ctx.args:
                            t = _str_const(ctx.args[0])
                            if t is not None:
                                inner_batch_table = t
                # Yield the With itself for the batch_alter_table table ref
                yield n, batch_table
                yield from walk(n.body, inner_batch_table)
                continue
            yield n, batch_table
            # Recurse into compound stmts
            for child in ast.iter_child_nodes(n):
                yield from walk([child], batch_table)

    yield from walk(func.body, None)


def _record_helper_call(m: Migration, table: str, call: ast.Call, helper_columns: set[str]) -> None:
    """Register a table as created via a local helper. Columns are the union
    of caller-supplied ``sa.Column`` args + helper-internal contributions."""
    m.creates_tables.add(table)
    for col in _column_names_from_call_args(call):
        m.creates_columns.add((table, col))
    for col in helper_columns:
        m.creates_columns.add((table, col))


def _record_for_loop_create_table(
    m: Migration,
    for_node: ast.For,
    column_helpers: dict[str, list[str]],
) -> None:
    """Recognize ``for X, ... in [(table_name, [columns]), ...]: op.create_table(X, *...)``.

    Only the most common shape from this repo is supported:
      - target is a Name or a Tuple whose first element is a Name
      - iter is a literal List/Tuple of literal Tuples whose first element is
        a string constant (the table name)
      - body contains ``op.create_table(<first-target-var>, ...)``
    """
    target_var: str | None = None
    if isinstance(for_node.target, ast.Name):
        target_var = for_node.target.id
    elif isinstance(for_node.target, ast.Tuple) and for_node.target.elts:
        first_target = for_node.target.elts[0]
        if isinstance(first_target, ast.Name):
            target_var = first_target.id
    if target_var is None or not isinstance(for_node.iter, (ast.List, ast.Tuple)):
        return

    # Map index-in-target-tuple → name (so we can resolve *extra_var from a 2nd
    # tuple element if needed).
    target_index_to_var: dict[int, str] = {}
    if isinstance(for_node.target, ast.Name):
        target_index_to_var[0] = for_node.target.id
    elif isinstance(for_node.target, ast.Tuple):
        for idx, elt in enumerate(for_node.target.elts):
            if isinstance(elt, ast.Name):
                target_index_to_var[idx] = elt.id

    # Inspect body: does it call op.create_table with the loop variable?
    body_create_table_calls: list[ast.Call] = []
    for sub in ast.walk(for_node):
        if isinstance(sub, ast.Call) and _is_op_call(sub, "create_table") and sub.args:
            first_arg = sub.args[0]
            if isinstance(first_arg, ast.Name) and first_arg.id == target_var:
                body_create_table_calls.append(sub)
    if not body_create_table_calls:
        return

    # Find which target index holds the column-list (if any). We look for
    # ``*<var>`` in the body's op.create_table args.
    starred_var_names: set[str] = set()
    for call in body_create_table_calls:
        for arg in call.args[1:]:
            if isinstance(arg, ast.Starred) and isinstance(arg.value, ast.Name):
                starred_var_names.add(arg.value.id)
    column_source_indices = {
        idx for idx, var in target_index_to_var.items() if var in starred_var_names
    }

    # Inline literal columns from the body's op.create_table calls (apply to
    # EVERY iteration since they don't depend on the loop var).
    body_literal_cols: set[str] = set()
    for call in body_create_table_calls:
        for col in _column_names_from_call_args(call):
            body_literal_cols.add(col)
        # Also expand any column_helper() call appearing as an arg.
        for arg in call.args[1:]:
            target_call: ast.Call | None = None
            if isinstance(arg, ast.Starred) and isinstance(arg.value, ast.Call):
                target_call = arg.value
            elif isinstance(arg, ast.Call):
                target_call = arg
            if target_call is None:
                continue
            tfunc = target_call.func
            if isinstance(tfunc, ast.Name) and tfunc.id in column_helpers:
                body_literal_cols.update(column_helpers[tfunc.id])

    for iter_elt in for_node.iter.elts:
        if not isinstance(iter_elt, (ast.Tuple, ast.List)):
            continue
        if not iter_elt.elts:
            continue
        table_name = _str_const(iter_elt.elts[0])
        if table_name is None:
            continue
        m.creates_tables.add(table_name)
        for col in body_literal_cols:
            m.creates_columns.add((table_name, col))
        # Pull columns from the tuple element that flows in via *splat
        for idx in column_source_indices:
            if idx < len(iter_elt.elts):
                source = iter_elt.elts[idx]
                if isinstance(source, (ast.List, ast.Tuple)):
                    for col_elt in source.elts:
                        if (
                            isinstance(col_elt, ast.Call)
                            and _is_sa_column(col_elt)
                            and col_elt.args
                        ):
                            cname = _str_const(col_elt.args[0])
                            if cname:
                                m.creates_columns.add((table_name, cname))


def _extract(path: Path) -> Migration | None:
    src = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return None
    revision, down, deps = _parse_revision_metadata(tree)
    if revision is None:
        return None
    m = Migration(revision=revision, path=path, down_revision=down, depends_on=deps)

    column_helpers = _collect_column_helpers(tree)
    table_helpers = _collect_table_helpers(tree, column_helpers)

    # First: scan upgrade() For-loops that emit op.create_table in their body
    # (a common bulk-table-creation pattern). The standard walker would also
    # see the inner op.create_table call but with the table name as a Name
    # node instead of a string Constant → it would silently skip it.
    upgrade_fn = _func_node(tree, "upgrade")
    if upgrade_fn is not None:
        for sub in ast.walk(upgrade_fn):
            if isinstance(sub, ast.For):
                _record_for_loop_create_table(m, sub, column_helpers)

    seen_nodes: set[int] = set()
    for node, batch_table in _walk_upgrade(tree):
        nid = id(node)
        if nid in seen_nodes:
            continue
        seen_nodes.add(nid)

        # The With's context_expr is op.batch_alter_table("X"): that's a ref.
        if isinstance(node, ast.With):
            for item in node.items:
                ctx = item.context_expr
                if isinstance(ctx, ast.Call) and _is_op_call(ctx, "batch_alter_table"):
                    if ctx.args:
                        t = _str_const(ctx.args[0])
                        if t is not None:
                            m.refs_tables.add(t)
            continue

        if not isinstance(node, ast.Call):
            continue

        # ---- local helper call: <_helper_name>("table", sa.Column(...), ...)
        if isinstance(node.func, ast.Name) and node.func.id in table_helpers:
            if node.args:
                t = _str_const(node.args[0])
                if t is not None:
                    _record_helper_call(m, t, node, table_helpers[node.func.id])
            continue

        # ---- table-creating ops ----
        if _is_op_call(node, "create_table"):
            if node.args:
                t = _str_const(node.args[0])
                if t is not None:
                    m.creates_tables.add(t)
                    for col in _column_names_from_create_table(node, column_helpers):
                        m.creates_columns.add((t, col))
            continue

        # ---- op.rename_table("old", "new"): "new" is created, "old" is ref ----
        # The new table inherits every column the old table had at rename
        # time. Columns are propagated in a post-processing pass once all
        # migrations are parsed (see `_propagate_renames`).
        if _is_op_call(node, "rename_table"):
            if len(node.args) >= 2:
                old_t = _str_const(node.args[0])
                new_t = _str_const(node.args[1])
                if old_t is not None:
                    m.refs_tables.add(old_t)
                if new_t is not None:
                    m.creates_tables.add(new_t)
                if old_t is not None and new_t is not None:
                    m.rename_edges.append((old_t, new_t))
            continue

        # ---- column-creating / table-touching ops ----
        if _is_op_call(node, "add_column"):
            if node.args:
                t = _str_const(node.args[0])
                if t is not None:
                    m.refs_tables.add(t)
                    col = _column_name_from_add_column(node)
                    if col:
                        m.creates_columns.add((t, col))
            continue

        # batch.add_column(sa.Column("c", ...))  → column on batch_table
        if batch_table is not None and _is_batch_call(node, "add_column"):
            col = _column_name_from_add_column(node)
            if col:
                m.creates_columns.add((batch_table, col))
            continue

        # ---- table-touching ops (ref only) ----
        if _is_op_call(node, "drop_column"):
            if node.args:
                t = _str_const(node.args[0])
                col = _str_const(node.args[1]) if len(node.args) > 1 else None
                if t is not None:
                    m.refs_tables.add(t)
                    if col is not None:
                        m.refs_columns.add((t, col))
            continue

        if _is_op_call(node, "alter_column"):
            if node.args:
                t = _str_const(node.args[0])
                col = _str_const(node.args[1]) if len(node.args) > 1 else None
                if t is not None:
                    m.refs_tables.add(t)
                    if col is not None:
                        m.refs_columns.add((t, col))
                        new_col = _str_kwarg(node, "new_column_name")
                        if new_col:
                            m.column_rename_edges.append((t, col, new_col))
                            m.creates_columns.add((t, new_col))
            continue

        if _is_op_call(node, "drop_table"):
            if node.args:
                t = _str_const(node.args[0])
                if t is not None:
                    m.refs_tables.add(t)
            continue

        # op.create_index(name, "T", [cols], ...)
        if _is_op_call(node, "create_index"):
            if len(node.args) >= 2:
                t = _str_const(node.args[1])
                if t is not None:
                    m.refs_tables.add(t)
                    if len(node.args) >= 3:
                        for col in _column_names_from_list(node.args[2]):
                            m.refs_columns.add((t, col))
            continue

        # op.create_foreign_key(name, "src", "ref", [src_cols], [ref_cols], ...)
        if _is_op_call(node, "create_foreign_key"):
            if len(node.args) >= 3:
                src_t = _str_const(node.args[1])
                ref_t = _str_const(node.args[2])
                if src_t is not None:
                    m.refs_tables.add(src_t)
                    if len(node.args) >= 4:
                        for col in _column_names_from_list(node.args[3]):
                            m.refs_columns.add((src_t, col))
                if ref_t is not None:
                    m.refs_tables.add(ref_t)
                    if len(node.args) >= 5:
                        for col in _column_names_from_list(node.args[4]):
                            m.refs_columns.add((ref_t, col))
            continue

        # op.create_unique_constraint(name, "T", [cols], ...)
        if _is_op_call(node, "create_unique_constraint"):
            if len(node.args) >= 2:
                t = _str_const(node.args[1])
                if t is not None:
                    m.refs_tables.add(t)
                    if len(node.args) >= 3:
                        for col in _column_names_from_list(node.args[2]):
                            m.refs_columns.add((t, col))
            continue

        # ---- batch.* ops (table is from with-statement) ----
        if batch_table is None:
            continue

        if _is_batch_call(node, "alter_column"):
            if node.args:
                col = _str_const(node.args[0])
                if col is not None:
                    m.refs_columns.add((batch_table, col))
                    new_col = _str_kwarg(node, "new_column_name")
                    if new_col:
                        m.column_rename_edges.append((batch_table, col, new_col))
                        m.creates_columns.add((batch_table, new_col))
            m.refs_tables.add(batch_table)
            continue

        if _is_batch_call(node, "drop_column"):
            if node.args:
                col = _str_const(node.args[0])
                if col is not None:
                    m.refs_columns.add((batch_table, col))
            m.refs_tables.add(batch_table)
            continue

        if _is_batch_call(node, "create_index"):
            if len(node.args) >= 2:
                for col in _column_names_from_list(node.args[1]):
                    m.refs_columns.add((batch_table, col))
            m.refs_tables.add(batch_table)
            continue

        if _is_batch_call(node, "create_unique_constraint"):
            if len(node.args) >= 2:
                for col in _column_names_from_list(node.args[1]):
                    m.refs_columns.add((batch_table, col))
            m.refs_tables.add(batch_table)
            continue

        if _is_batch_call(node, "create_foreign_key"):
            # batch.create_foreign_key(name, ref_table, [src_cols], [ref_cols])
            if len(node.args) >= 2:
                ref_t = _str_const(node.args[1])
                if ref_t is not None:
                    m.refs_tables.add(ref_t)
                m.refs_tables.add(batch_table)
                if len(node.args) >= 3:
                    for col in _column_names_from_list(node.args[2]):
                        m.refs_columns.add((batch_table, col))
                if ref_t is not None and len(node.args) >= 4:
                    for col in _column_names_from_list(node.args[3]):
                        m.refs_columns.add((ref_t, col))
            continue

    return m


# ---------------------------------------------------------------------------
# DAG
# ---------------------------------------------------------------------------


def _collect_all() -> dict[str, Migration]:
    out: dict[str, Migration] = {}
    for p in sorted(MIGRATIONS_DIR.glob("*.py")):
        m = _extract(p)
        if m is not None:
            out[m.revision] = m
    _propagate_renames(out)
    return out


def _propagate_renames(migrations: dict[str, Migration]) -> None:
    """After all migrations are parsed, propagate columns through table-rename
    edges.

    For each migration ``M`` that does ``op.rename_table("old", "new")``, every
    column previously created on ``"old"`` by some ancestor of ``M`` is now
    available on ``"new"`` from ``M`` onward. We record those columns as
    created by ``M`` itself — that way the audit step sees ``M`` as the
    creator-of-record for the renamed columns on the new name, and downstream
    migrations that reference ``new.col`` find a creator in their predecessor
    closure (provided they descend from ``M``).
    """
    preds = _build_predecessors(migrations)

    # Index columns per table → revision-set that creates them.
    columns_by_table: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for m in migrations.values():
        for t, c in m.creates_columns:
            columns_by_table[t][c].add(m.revision)

    for m in migrations.values():
        if not m.rename_edges:
            continue
        m_preds = preds[m.revision]
        for old, new in m.rename_edges:
            for col, creators in columns_by_table.get(old, {}).items():
                if creators & m_preds:
                    m.creates_columns.add((new, col))


def _build_predecessors(migrations: dict[str, Migration]) -> dict[str, set[str]]:
    """For each migration, compute the set of all transitively-reachable
    predecessor revision ids via ``down_revision`` ∪ ``depends_on``.

    Missing parents are ignored (treated as roots) — they typically indicate a
    revision referenced but not present in the repo, which would be a separate
    bug. This analyzer does not flag those (out of scope)."""
    cache: dict[str, set[str]] = {}

    def visit(rev: str, stack: set[str]) -> set[str]:
        if rev in cache:
            return cache[rev]
        if rev in stack:
            return set()  # cycle guard (should not happen in alembic DAG)
        stack.add(rev)
        m = migrations.get(rev)
        if m is None:
            return set()
        result: set[str] = set()
        for parent in (*m.down_revision, *m.depends_on):
            if parent in migrations:
                result.add(parent)
                result.update(visit(parent, stack))
        stack.discard(rev)
        cache[rev] = result
        return result

    return {rev: visit(rev, set()) for rev in migrations}


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


def _audit(migrations: dict[str, Migration]) -> list[Violation]:
    preds = _build_predecessors(migrations)

    # Index: who creates each (table) and each (table, column)?
    table_creators: dict[str, set[str]] = defaultdict(set)
    column_creators: dict[tuple[str, str], set[str]] = defaultdict(set)
    for m in migrations.values():
        for t in m.creates_tables:
            table_creators[t].add(m.revision)
        for tc in m.creates_columns:
            column_creators[tc].add(m.revision)

    violations: list[Violation] = []

    for m in migrations.values():
        scope = preds[m.revision] | {m.revision}
        guarded = RUNTIME_GUARDED_TABLE_REFS.get(m.revision, frozenset())

        for t in sorted(m.refs_tables):
            if t in ALEMBIC_INTERNAL_TABLES:
                continue
            if t in guarded:
                continue
            creators = table_creators.get(t, set())
            if not creators:
                violations.append(
                    Violation(
                        migration=m.revision,
                        file=str(m.path.relative_to(REPO_ROOT)),
                        table=t,
                        column=None,
                        why=f"no migration in the entire repo creates table {t!r}",
                    )
                )
            elif not (creators & scope):
                violations.append(
                    Violation(
                        migration=m.revision,
                        file=str(m.path.relative_to(REPO_ROOT)),
                        table=t,
                        column=None,
                        why=(
                            f"table {t!r} created by {sorted(creators)!r}; "
                            f"none are in down_revision/depends_on closure of "
                            f"{m.revision!r}. Fix: declare depends_on=(<creator>,)."
                        ),
                    )
                )

        for t, col in sorted(m.refs_columns):
            if t in ALEMBIC_INTERNAL_TABLES or t in guarded:
                continue
            # If the table itself is missing, the table-level violation above
            # is enough — no need to also flag every column ref.
            t_creators = table_creators.get(t, set())
            if not t_creators or not (t_creators & scope):
                continue
            col_creators = column_creators.get((t, col), set())
            if not col_creators:
                violations.append(
                    Violation(
                        migration=m.revision,
                        file=str(m.path.relative_to(REPO_ROOT)),
                        table=t,
                        column=col,
                        why=(
                            f"no migration in the entire repo creates column "
                            f"{t}.{col}. Either a column-add migration is missing, "
                            f"or this reference is a typo."
                        ),
                    )
                )
            elif not (col_creators & scope):
                violations.append(
                    Violation(
                        migration=m.revision,
                        file=str(m.path.relative_to(REPO_ROOT)),
                        table=t,
                        column=col,
                        why=(
                            f"column {t}.{col} created by {sorted(col_creators)!r}; "
                            f"none are in down_revision/depends_on closure of "
                            f"{m.revision!r}. Fix: declare depends_on=(<creator>,)."
                        ),
                    )
                )

    return violations


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_migrations_dir_exists() -> None:
    """Sanity: target directory is non-empty."""
    assert MIGRATIONS_DIR.is_dir(), f"missing migrations dir: {MIGRATIONS_DIR}"
    assert any(MIGRATIONS_DIR.glob("*.py")), "no *.py migrations found"


def test_every_migration_has_revision_id() -> None:
    """Sanity: every parsed migration produced a non-empty revision id. If
    this regresses, the analyzer is silently dropping files."""
    migrations = _collect_all()
    assert migrations, "no migrations parsed"
    for rev in migrations:
        assert rev, "empty revision id"


def test_no_cross_branch_uncreated_dependencies() -> None:
    """Pin: every table / column referenced by an Alembic structured op call
    in any migration must trace to a creator that is either the migration
    itself or in its transitive ``down_revision``/``depends_on`` predecessor
    set.

    Violations are either:
      - **Cross-branch dep**: creator exists, but on a different branch the
        current migration doesn't depend on → ``alembic upgrade head`` can pick
        an ordering where the touch precedes the create.
      - **Missing migration**: no creator in the repo → reference is dead and
        will always fail on a fresh database.

    Fix recipe (iter-9 PR #557 commit ``ab0679c`` is the reference): add
    ``depends_on = ("<creator-revision>",)`` at module level. The downgrade
    path is left untouched.
    """
    migrations = _collect_all()
    violations = _audit(migrations)
    if violations:
        lines = []
        for v in violations:
            target = v.table if v.column is None else f"{v.table}.{v.column}"
            lines.append(f"  {v.file}  rev={v.migration}  ref={target}\n    {v.why}")
        raise AssertionError(
            f"Found {len(violations)} cross-branch / missing dependency violation(s) "
            "in alembic migrations. Each one will cause `alembic upgrade head` to "
            "fail on a fresh Postgres database under at least one valid topological "
            "ordering of the DAG.\n\n" + "\n".join(lines)
        )


if __name__ == "__main__":
    migrations = _collect_all()
    print(f"Parsed {len(migrations)} migrations.")
    violations = _audit(migrations)
    if violations:
        print(f"\nVIOLATIONS: {len(violations)}")
        for v in violations:
            target = v.table if v.column is None else f"{v.table}.{v.column}"
            print(f"  {v.file}")
            print(f"    rev: {v.migration}")
            print(f"    ref: {target}")
            print(f"    why: {v.why}")
        sys.exit(1)
    print("OK — no cross-branch / missing dependency violations found.")
    sys.exit(0)
