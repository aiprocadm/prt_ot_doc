"""Comprehensive pin-test: Alembic migrations must avoid 5 known classes of
``alembic-postgres-upgrade`` failure.

This is the *proactive* analyzer that consolidates the bug classes uncovered
reactively in iter-7..14 (one fix per iteration, see PRs #553/#555/#557/#559/
#561/#563/#564 and iter-14 fix commit c66d4f1). It runs on every backend test
invocation; new violations are blocking — fix the migration before merging.

The 5 antipattern classes
=========================

A1 — enum double-create
-----------------------
Symptom::

    asyncpg.exceptions.DuplicateObjectError: type "<name>" already exists
    [SQL: CREATE TYPE <name> AS ENUM (...)]

Cause: migration calls ``<enum>.create(bind, checkfirst=True)`` AND also uses
``sa.Enum(name=X)`` (without ``create_type=False``) in a downstream
``op.create_table`` / ``op.add_column``. SQLAlchemy 2.x auto-emits the CREATE
TYPE for ``sa.Enum`` inside ``op.create_table``; the explicit ``.create()``
then runs a second CREATE TYPE and Postgres raises DuplicateObjectError.

Fix: declare the enum as ``postgresql.ENUM(..., name=X, create_type=False)``
so SQLAlchemy does NOT auto-emit, and rely on the explicit ``.create()``.

A2 — GIN index on non-JSONB column
----------------------------------
Symptom::

    asyncpg.exceptions.UndefinedObjectError: data type json has no default
    operator class for access method "gin"

Cause: ``op.create_index(..., postgresql_using="gin")`` OR raw
``op.execute("CREATE INDEX ... USING GIN (col)")`` where ``col`` is declared
``sa.JSON()`` (not ``postgresql.JSONB``). Postgres has no built-in opclass
for ``json``; the opclass exists for ``jsonb``. Plain text columns are OK
*only* when an explicit non-default opclass is given (e.g. ``gin_trgm_ops``
from the ``pg_trgm`` extension).

Fix: switch the column to
``postgresql.JSONB(astext_type=sa.Text())`` with
``server_default=sa.text("'{}'::jsonb")``; alternatively, add an explicit
opclass (``USING GIN (col gin_trgm_ops)``).

A3 — drop-recreate enum on dependent column
-------------------------------------------
Symptom::

    asyncpg.exceptions.DependentObjectsStillExistError: cannot drop type
    <name> because other objects depend on it

Cause: the migration calls ``<enum>.drop(...)`` followed within a few
statements by ``<enum>.create(...)`` (intent: extend the enum's value list).
But some predecessor migration already added a column of that type; Postgres
refuses to drop the type until every dependent column is removed first.

Fix: split the migration. Add new values in-place with
``ALTER TYPE <name> ADD VALUE IF NOT EXISTS '<v>'`` (under a PG dialect
gate), and put any data ``UPDATE`` referencing the new values in a *separate*
follow-up revision (``<X>b_<topic>_data.py``) — Postgres ≥12 forbids
referencing a newly-added enum value in the same transaction. Precedent:
``next55`` → ``next55`` + ``next55b`` split (PR #564).

A4 — cross-branch table/column reference without ``depends_on``
---------------------------------------------------------------
Symptom: ``alembic upgrade head`` fails on a fresh DB with
``UndefinedTableError`` / ``UndefinedColumnError`` — a column was added to
table ``X`` whose creator migration is on a different branch and not yet
applied at the point the dependent migration runs.

Cause: the dependent migration's ``down_revision`` chain does not include
the creator's branch and ``depends_on`` is unset, so Alembic's topological
sort can interleave them incorrectly.

Fix: add ``depends_on = ("<creator-rev>",)`` to the top of the dependent
migration.

A5 — unsafe use of newly-added enum value (iter-14)
---------------------------------------------------
Symptom::

    asyncpg.exceptions.UnsafeNewEnumValueUsageError: unsafe use of new
    value "<X>" of enum type <name>
    HINT:  New enum values must be committed before they can be used.

Cause: env.py wraps the entire ``alembic upgrade head`` in one outer async
transaction (``async with connectable.begin() as connection``). All
revisions share that single tx. Postgres ≥12 forbids using a newly-added
enum value in the same transaction where it was added via ``ALTER TYPE
ADD VALUE``. So if *any* revision in the upgrade chain (including the
current one or any of its predecessors) does ``ALTER TYPE <name> ADD VALUE
'<X>'``, then NO revision in the chain may reference ``'<X>'`` from a SQL
DML statement (``UPDATE``/``INSERT``/``WHERE``) targeted at a column of
type ``<name>``. Splitting the ALTER and the UPDATE into separate alembic
revisions does NOT help — they still share the outer tx.

History: CI run 26294051531 exposed this class via the iter-13 next55
split. iter-13 had assumed alembic enforces a transaction-per-revision
boundary; the env.py outer transaction invalidates that assumption.

Fix recommendations (in priority order):
  1. **Remove the data UPDATE entirely** if existing rows have valid
     alternative values in the extended enum (often true, since
     ``ALTER TYPE ADD VALUE`` preserves existing column values). This is
     the iter-14 fix (PR #564, commit c66d4f1) — the legacy
     ``{DRAFT, ACTIVE, ARCHIVED}`` states remain valid in the extended
     ``{DRAFT, ACTIVE, ARCHIVED, UPLOADED, LINTED, READY, DEPRECATED}``
     so no backfill is needed.
  2. **Move the data migration to an app-level startup hook** or a
     one-shot CLI command (``app.cli.main ...``) that runs *after*
     ``alembic upgrade head`` completes — at that point the new values
     are catalog-committed and may be referenced.
  3. **Refactor env.py to drop the outer transaction** — most invasive;
     affects every migration and warrants its own discussion. Out of
     scope for iter-14.

Detection scope (narrow on purpose to avoid false positives): only flags
the pattern ``ALTER TYPE <enum> ADD VALUE '<V>'`` in some revision
(itself or any predecessor) paired with ``op.execute("UPDATE <t> SET
<col> = '<V>' ...")`` / ``... = '<V>'`` where ``(t, col)`` is a known
column of type ``ENUM:<enum>``. INSERT / WHERE forms are detected as
secondary heuristics. Strings that don't resolve to a known enum column
are silently skipped (no false-positive A5 noise from arbitrary SQL).

Visitor architecture
====================
Each antipattern has its own dedicated visitor — keeps each visitor small,
its violation message specific, and any one visitor easily disable-able if
needed. The shared DAG / predecessor-closure machinery is computed once per
``find_violations()`` call and threaded into each visitor.

For A4 we reuse the implementation from
``tests/test_migrations_cross_branch_deps.py`` rather than re-write it —
that file is ~1k lines of careful FP-filtering (table-helper inlining,
batch-alter-table tracking, for-loop create-table support, rename
propagation) and any port would risk drift.

History
-------
* iter-7  (PRs #553/#554): single-migration A1 fix.
* iter-8  (PR #555): A1 extended to 7 more migrations.
* iter-9  (PR #557): A1 closed for 4 more + class-3 (uncreated enum) +
  point-wise A4 fix for ``20250501``.
* iter-10 (PR #559): structural A4 pin-test added (cross-branch DAG walk).
* iter-11 (PR #561): A2 fix for ``20260318_next47_files_metadata_archive``.
* iter-12 (PR #563): single ``ALTER TYPE ADD VALUE`` hotfix (precursor to A3).
* iter-13 (PR #564): A3 fix — split ``next55`` into ``next55`` + ``next55b``.
* iter-14 (this PR):
    - Unified analyzer covering A1+A2+A3+A4+A5 in one pass.
    - A5 added in response to CI run 26294051531
      (``UnsafeNewEnumValueUsageError`` on ``templateversion.status =
      'UPLOADED'`` despite the iter-13 next55/next55b split).
    - The actual repo-level A5 fix lives in commit c66d4f1: the lossy
      ``UPDATE templateversion SET status = 'UPLOADED'`` was removed
      because legacy values remain valid under ``ALTER TYPE ADD VALUE``.

Running locally without pytest (Windows+Py3.13 conftest hang workaround)
------------------------------------------------------------------------
::

    python tests/test_migrations_comprehensive_safety.py

Exits 0 on no violations, 1 with a printed per-class breakdown otherwise.
"""

from __future__ import annotations

import ast
import re
import sys
from collections import defaultdict
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS_DIR = REPO_ROOT / "backend" / "app" / "migrations" / "versions"

# Direct-invocation support: when run as ``python tests/test_migrations_..._.py``,
# the parent directory is not on sys.path, so ``from tests.X import Y`` fails.
# Inject the repo root so the cross-branch helpers below import cleanly.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Reuse the cross-branch DAG / predecessor machinery from the existing
# narrow-guard test. That implementation has tuned FP-filtering for the
# table-helper / batch-alter-table / for-loop patterns in this repo; porting
# it inline would risk drift.
from tests.test_migrations_cross_branch_deps import (  # noqa: E402
    _audit as _xbranch_audit,
    _collect_all as _xbranch_collect_all,
)


# ---------------------------------------------------------------------------
# Shared AST helpers
# ---------------------------------------------------------------------------


def _safe_rel(path: Path) -> Path | str:
    """Return ``path.relative_to(REPO_ROOT)`` when ``path`` lives inside the
    repo, else fall back to the bare filename. Lets the synthetic-violation
    tests use ``tmp_path`` (which is typically on a different filesystem
    root, especially on Windows) without forcing the per-visitor message
    builders to special-case external paths.
    """
    try:
        return path.relative_to(REPO_ROOT)
    except ValueError:
        return path.name


def _str_const(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _str_kwarg(call: ast.Call, name: str) -> str | None:
    for kw in call.keywords:
        if kw.arg == name:
            return _str_const(kw.value)
    return None


def _kw_value(call: ast.Call, name: str) -> ast.AST | None:
    for kw in call.keywords:
        if kw.arg == name:
            return kw.value
    return None


def _func_node(tree: ast.Module, name: str) -> ast.FunctionDef | None:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    return None


def _func_lineno_range(tree: ast.Module, name: str) -> tuple[int, int] | None:
    node = _func_node(tree, name)
    if node is None:
        return None
    end = getattr(node, "end_lineno", None)
    return node.lineno, end if end is not None else sys.maxsize


def _is_attr_call(call: ast.Call, owner: str | None, attr: str) -> bool:
    func = call.func
    if not isinstance(func, ast.Attribute) or func.attr != attr:
        return False
    if owner is None:
        return True
    return isinstance(func.value, ast.Name) and func.value.id == owner


def _is_op_call(call: ast.Call, attr: str) -> bool:
    return _is_attr_call(call, "op", attr)


def _module_assigns(tree: ast.Module) -> dict[str, ast.AST]:
    out: dict[str, ast.AST] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    out[target.id] = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.value is not None:
                out[node.target.id] = node.value
    return out


def _str_tuple(node: ast.AST | None) -> tuple[str, ...]:
    if node is None or (isinstance(node, ast.Constant) and node.value is None):
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


def _parse_revision_metadata(tree: ast.Module) -> tuple[str | None, tuple[str, ...], tuple[str, ...]]:
    assigns = _module_assigns(tree)
    rev = _str_const(assigns.get("revision"))
    down = _str_tuple(assigns.get("down_revision"))
    deps = _str_tuple(assigns.get("depends_on"))
    return rev, down, deps


# ---------------------------------------------------------------------------
# Cross-migration index: which columns are of which enum/SQL type?
# ---------------------------------------------------------------------------


def _is_sa_column(call: ast.Call) -> bool:
    func = call.func
    if isinstance(func, ast.Attribute) and func.attr == "Column":
        return isinstance(func.value, ast.Name) and func.value.id == "sa"
    if isinstance(func, ast.Name) and func.id == "Column":
        return True
    return False


def _enum_call_name(call: ast.Call) -> str | None:
    """For ``sa.Enum(..., name="X")`` or ``postgresql.ENUM(..., name="X")``
    return X, else None."""
    func = call.func
    if not (isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name)):
        return None
    if not (
        (func.attr == "Enum" and func.value.id == "sa")
        or (func.attr == "ENUM" and func.value.id == "postgresql")
    ):
        return None
    return _str_kwarg(call, "name")


def _resolve_column_type(type_node: ast.AST | None, enum_var_to_name: dict[str, str]) -> str:
    """Map a SQLAlchemy type-arg AST node to a short canonical-type label.

    Recognized labels:
      * "JSONB", "JSON", "TSVECTOR", "ARRAY", "TEXT", "STRING", "INTEGER",
        "BIGINTEGER", "BOOLEAN", "DATETIME", "ENUM:<enum_name>", "ENUM:?",
        or "?" when unrecognized.

    ``enum_var_to_name`` maps a module-level enum-variable name → enum type
    name; used to resolve ``sa.Column("c", my_enum_var)`` style declarations.
    """
    if type_node is None:
        return "?"
    if isinstance(type_node, ast.Call):
        # Enum constructor inline: sa.Enum(..., name="X") / postgresql.ENUM(..., name="X")
        enum_name = _enum_call_name(type_node)
        if enum_name is not None:
            return f"ENUM:{enum_name}"
        func = type_node.func
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            attr = func.attr.upper()
            owner = func.value.id
            if owner == "postgresql" and attr == "JSONB":
                return "JSONB"
            if owner == "postgresql" and attr == "JSON":
                return "JSON"
            if owner == "postgresql" and attr == "TSVECTOR":
                return "TSVECTOR"
            if owner == "postgresql" and attr == "ARRAY":
                return "ARRAY"
            if owner == "postgresql" and attr == "TEXT":
                return "TEXT"
            if owner == "sa":
                return {
                    "JSON": "JSON",
                    "TEXT": "TEXT",
                    "STRING": "STRING",
                    "INTEGER": "INTEGER",
                    "BIGINTEGER": "BIGINTEGER",
                    "BOOLEAN": "BOOLEAN",
                    "DATETIME": "DATETIME",
                    "DATE": "DATE",
                    "FLOAT": "FLOAT",
                    "NUMERIC": "NUMERIC",
                    "LARGEBINARY": "LARGEBINARY",
                }.get(attr, attr)
        # Bare Type() form, e.g. JSONB() with module-level import alias.
        if isinstance(func, ast.Name):
            name = func.id.upper()
            if name in {"JSONB", "JSON", "TSVECTOR", "ARRAY", "TEXT", "STRING"}:
                return name
        return "?"
    if isinstance(type_node, ast.Name):
        # Bare reference: ``my_enum_var``, ``JSONB``, ``Text`` etc.
        if type_node.id in enum_var_to_name:
            return f"ENUM:{enum_var_to_name[type_node.id]}"
        upper = type_node.id.upper()
        if upper in {"JSONB", "JSON", "TSVECTOR", "ARRAY", "TEXT"}:
            return upper
        return "?"
    if isinstance(type_node, ast.Attribute):
        # ``postgresql.JSONB`` as a class (not called)
        if isinstance(type_node.value, ast.Name):
            attr = type_node.attr.upper()
            if attr in {"JSONB", "JSON", "TSVECTOR", "ARRAY", "TEXT"}:
                return attr
        return "?"
    return "?"


def _collect_enum_var_to_name(tree: ast.Module) -> dict[str, str]:
    """Map module/function-level ``var = sa.Enum(..., name="X")`` (or
    ``postgresql.ENUM(..., name="X")``) → "X". Searches whole tree."""
    out: dict[str, str] = {}
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Assign) and isinstance(node.value, ast.Call)):
            continue
        enum_name = _enum_call_name(node.value)
        if enum_name is None:
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                out[target.id] = enum_name
    return out


def _columns_created_by_migration(tree: ast.Module) -> dict[tuple[str, str], str]:
    """Return ``{(table, column): type_label}`` for every column declared in
    this migration's ``upgrade()`` body via:

      * ``op.create_table("T", sa.Column("c", <type>, ...), ...)``
      * ``op.add_column("T", sa.Column("c", <type>, ...))``
      * inside ``with op.batch_alter_table("T") as batch: batch.add_column(sa.Column("c", <type>, ...))``

    ``type_label`` is computed by ``_resolve_column_type``.
    """
    enum_var_to_name = _collect_enum_var_to_name(tree)
    upgrade_fn = _func_node(tree, "upgrade")
    if upgrade_fn is None:
        return {}

    out: dict[tuple[str, str], str] = {}

    def _column_args(call: ast.Call) -> tuple[str | None, ast.AST | None]:
        """Return (column_name, type_arg_node) from a sa.Column(...) call."""
        if not call.args:
            return None, None
        name = _str_const(call.args[0])
        if len(call.args) >= 2:
            return name, call.args[1]
        return name, _kw_value(call, "type_")

    def _record_from_create_table(call: ast.Call) -> None:
        if not call.args:
            return
        t = _str_const(call.args[0])
        if t is None:
            return
        for arg in call.args[1:]:
            candidates: list[ast.Call] = []
            if isinstance(arg, ast.Call) and _is_sa_column(arg):
                candidates.append(arg)
            elif isinstance(arg, (ast.List, ast.Tuple)):
                for elt in arg.elts:
                    if isinstance(elt, ast.Call) and _is_sa_column(elt):
                        candidates.append(elt)
            for col_call in candidates:
                name, type_arg = _column_args(col_call)
                if name is None:
                    continue
                out[(t, name)] = _resolve_column_type(type_arg, enum_var_to_name)

    def _record_from_add_column(table: str, col_call: ast.Call) -> None:
        name, type_arg = _column_args(col_call)
        if name is None:
            return
        out[(table, name)] = _resolve_column_type(type_arg, enum_var_to_name)

    def _walk(nodes: list, batch_table: str | None) -> None:
        for n in nodes:
            if isinstance(n, ast.With):
                inner_batch = batch_table
                for item in n.items:
                    ctx = item.context_expr
                    if isinstance(ctx, ast.Call) and _is_op_call(ctx, "batch_alter_table"):
                        if ctx.args:
                            t = _str_const(ctx.args[0])
                            if t is not None:
                                inner_batch = t
                _walk(list(n.body), inner_batch)
                continue
            # Recurse into compound stmts first to find calls.
            if isinstance(n, ast.Call):
                if _is_op_call(n, "create_table"):
                    _record_from_create_table(n)
                elif _is_op_call(n, "add_column") and len(n.args) >= 2:
                    t = _str_const(n.args[0])
                    if t is not None:
                        sub = n.args[1]
                        if isinstance(sub, ast.Call) and _is_sa_column(sub):
                            _record_from_add_column(t, sub)
                elif (
                    batch_table is not None
                    and isinstance(n.func, ast.Attribute)
                    and n.func.attr == "add_column"
                    and n.args
                    and isinstance(n.args[0], ast.Call)
                    and _is_sa_column(n.args[0])
                ):
                    _record_from_add_column(batch_table, n.args[0])
            # Recurse
            for child in ast.iter_child_nodes(n):
                _walk([child], batch_table)

    _walk(list(upgrade_fn.body), None)
    return out


def _build_column_type_index() -> tuple[
    dict[str, dict[tuple[str, str], str]],
    dict[str, set[str]],
    dict[str, str],
    dict[str, Path],
]:
    """One pass over ``MIGRATIONS_DIR`` building:

      * ``per_migration``: ``rev → {(table, col): type_label}`` from upgrade()
      * ``predecessors``: ``rev → set[rev]`` transitive closure
      * ``rev_of_file``: ``filename → revision_id``
      * ``path_of_rev``: ``rev → Path``
    """
    per_migration: dict[str, dict[tuple[str, str], str]] = {}
    rev_meta: dict[str, dict] = {}
    rev_of_file: dict[str, str] = {}
    path_of_rev: dict[str, Path] = {}

    for path in sorted(MIGRATIONS_DIR.glob("*.py")):
        src = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        rev, down, deps = _parse_revision_metadata(tree)
        if rev is None:
            continue
        per_migration[rev] = _columns_created_by_migration(tree)
        rev_meta[rev] = {"down": down, "deps": deps}
        rev_of_file[path.name] = rev
        path_of_rev[rev] = path

    # Predecessor closure (subset of cross_branch's _build_predecessors,
    # operating on the dict shape above rather than Migration dataclass).
    cache: dict[str, set[str]] = {}

    def visit(rev: str, stack: set[str]) -> set[str]:
        if rev in cache:
            return cache[rev]
        if rev in stack:
            return set()
        stack.add(rev)
        meta = rev_meta.get(rev)
        if meta is None:
            return set()
        result: set[str] = set()
        for parent in (*meta["down"], *meta["deps"]):
            if parent in rev_meta:
                result.add(parent)
                result.update(visit(parent, stack))
        stack.discard(rev)
        cache[rev] = result
        return result

    predecessors = {rev: visit(rev, set()) for rev in rev_meta}
    return per_migration, predecessors, rev_of_file, path_of_rev


def _lookup_column_type(
    table: str,
    column: str,
    scope: set[str],
    per_migration: dict[str, dict[tuple[str, str], str]],
) -> str:
    """Return the most-recent type label for ``(table, column)`` across the
    revisions in ``scope`` (which should be ``{self_rev} | predecessors``).

    For columns altered in multiple migrations, we prefer the LATEST type
    declaration (so an ``alter_column`` that switches JSON→JSONB is honored).
    We approximate "latest" by revision-id lexicographic sort — the repo's
    ID convention prefixes by date, so this is monotonic enough for the
    purposes of this analyzer.
    """
    found: list[tuple[str, str]] = []
    for rev in scope:
        cols = per_migration.get(rev, {})
        t = cols.get((table, column))
        if t is not None:
            found.append((rev, t))
    if not found:
        return "?"
    found.sort()
    return found[-1][1]


# ---------------------------------------------------------------------------
# A1 — enum double-create
# ---------------------------------------------------------------------------


def _a1_uses_create_checkfirst(tree: ast.Module) -> bool:
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "create"):
            continue
        for kw in node.keywords:
            if (
                kw.arg == "checkfirst"
                and isinstance(kw.value, ast.Constant)
                and kw.value.value is True
            ):
                return True
    return False


def _a1_enum_call_kind(call: ast.Call) -> tuple[str, str] | None:
    func = call.func
    if not isinstance(func, ast.Attribute) or not isinstance(func.value, ast.Name):
        return None
    name_kw = _str_kwarg(call, "name")
    if name_kw is None:
        return None
    if func.attr == "Enum" and func.value.id == "sa":
        return ("sa.Enum", name_kw)
    if func.attr == "ENUM" and func.value.id == "postgresql":
        return ("postgresql.ENUM", name_kw)
    return None


def _a1_has_create_type_false(call: ast.Call) -> bool:
    for kw in call.keywords:
        if (
            kw.arg == "create_type"
            and isinstance(kw.value, ast.Constant)
            and kw.value.value is False
        ):
            return True
    return False


def _a1_audit_one(path: Path) -> list[str]:
    src = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(src)
    except SyntaxError as exc:
        return [
            f"{_safe_rel(path)}:{exc.lineno or 0}  parse error: {exc}"
        ]
    if not _a1_uses_create_checkfirst(tree):
        return []
    downgrade_range = _func_lineno_range(tree, "downgrade")
    out: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        match = _a1_enum_call_kind(node)
        if match is None:
            continue
        call_str, enum_name = match
        if (
            downgrade_range is not None
            and downgrade_range[0] <= node.lineno <= downgrade_range[1]
        ):
            continue
        if _a1_has_create_type_false(node):
            continue
        out.append(
            f"{_safe_rel(path)}:{node.lineno}  "
            f"{call_str}(name={enum_name!r}) — missing create_type=False; "
            "fix: switch to postgresql.ENUM(..., name=X, create_type=False)"
        )
    return out


# ---------------------------------------------------------------------------
# A2 — GIN index on non-JSONB column
# ---------------------------------------------------------------------------


GIN_COMPATIBLE_TYPES: frozenset[str] = frozenset({"JSONB", "TSVECTOR", "ARRAY"})

# When an explicit non-default opclass is given (e.g. ``gin_trgm_ops``,
# ``gin_jsonb_ops``), GIN is valid regardless of base column type. We detect
# the presence of "_ops" (or known opclass names) in the SQL after the column
# name to skip such cases.
_OPCLASS_PATTERN = re.compile(r"\bgin_\w+_ops\b", re.IGNORECASE)


def _a2_audit_one(
    path: Path,
    rev: str | None,
    scope: set[str],
    per_migration: dict[str, dict[tuple[str, str], str]],
) -> list[str]:
    """Flag GIN-on-non-JSONB violations.

    Notes on precision:
      * Columns whose type cannot be resolved (returns ``"?"`` from
        ``_lookup_column_type``) are SKIPPED rather than reported as JSON.
        Reporting them would produce false positives whenever a column is
        declared in a part of the codebase the AST index does not parse
        (e.g., an out-of-scope ancestor migration with unusual idioms, or
        a column declared inside a helper function not unrolled by the
        index). The trade-off: a genuine GIN-on-JSON bug whose column AST
        we fail to parse will slip through. This is preferable to
        flagging cleanly-typed columns as suspect.
      * Columns of a GIN-compatible type
        (``JSONB``/``TSVECTOR``/``ARRAY``) are silently accepted.
      * An explicit opclass via ``postgresql_ops={"col":
        "gin_trgm_ops"}`` or ``USING GIN (col gin_trgm_ops)`` short-
        circuits the check at the index level (we trust the engineer).
    """
    src = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return []
    upgrade_fn = _func_node(tree, "upgrade")
    if upgrade_fn is None:
        return []
    out: list[str] = []
    rel = _safe_rel(path)
    for node in ast.walk(upgrade_fn):
        if not isinstance(node, ast.Call):
            continue
        # Form 1: op.create_index(..., postgresql_using="gin")
        if _is_op_call(node, "create_index"):
            using = _str_kwarg(node, "postgresql_using")
            if (using or "").lower() != "gin":
                continue
            # Skip cases that specify an explicit opclass via
            # postgresql_ops={"col": "gin_trgm_ops"} kwarg.
            ops_kw = _kw_value(node, "postgresql_ops")
            if isinstance(ops_kw, ast.Dict):
                # If any value contains "_ops", trust it.
                opclass_present = False
                for v in ops_kw.values:
                    if isinstance(v, ast.Constant) and isinstance(v.value, str):
                        if _OPCLASS_PATTERN.search(v.value):
                            opclass_present = True
                            break
                if opclass_present:
                    continue
            # Determine the table name and column list.
            table = None
            cols: list[str] = []
            if len(node.args) >= 2:
                table = _str_const(node.args[1])
            cols_node = node.args[2] if len(node.args) >= 3 else _kw_value(node, "columns")
            if isinstance(cols_node, (ast.List, ast.Tuple)):
                for elt in cols_node.elts:
                    s = _str_const(elt)
                    if s is not None:
                        cols.append(s)
            if table is None:
                continue
            for col in cols:
                actual = _lookup_column_type(table, col, scope, per_migration)
                # Skip unknown-type columns to avoid false-positives.
                if actual == "?":
                    continue
                if actual not in GIN_COMPATIBLE_TYPES:
                    out.append(
                        f"{rel}:{node.lineno}  "
                        f"op.create_index(..., postgresql_using='gin') over "
                        f"{table}.{col} of type {actual!r} — Postgres has no "
                        "default GIN opclass for this type. Fix: switch the "
                        "column to postgresql.JSONB or add an explicit opclass "
                        "via postgresql_ops={'col': 'gin_<...>_ops'}."
                    )
        # Form 2: op.execute("CREATE INDEX ... USING GIN (col)")
        elif _is_op_call(node, "execute") and len(node.args) == 1:
            arg = node.args[0]
            if not (isinstance(arg, ast.Constant) and isinstance(arg.value, str)):
                continue
            sql = arg.value
            if "USING GIN" not in sql.upper():
                continue
            # Skip if a known opclass appears in the column expression.
            if _OPCLASS_PATTERN.search(sql):
                continue
            m = re.search(
                r"CREATE\s+INDEX(?:\s+IF\s+NOT\s+EXISTS)?\s+\S+\s+ON\s+(\w+)\s+"
                r"USING\s+GIN\s*\(\s*(\w+)",
                sql,
                re.IGNORECASE,
            )
            if not m:
                continue
            table, col = m.group(1), m.group(2)
            actual = _lookup_column_type(table, col, scope, per_migration)
            # Skip unknown-type columns to avoid false-positives.
            if actual == "?":
                continue
            if actual not in GIN_COMPATIBLE_TYPES:
                out.append(
                    f"{rel}:{node.lineno}  "
                    f"op.execute('CREATE INDEX ... USING GIN ({col})') on "
                    f"{table}.{col} of type {actual!r} — Postgres has no "
                    "default GIN opclass for this type. Fix: switch the column "
                    "to JSONB, or add an explicit opclass "
                    "(USING GIN (col gin_<...>_ops))."
                )
    return out


# ---------------------------------------------------------------------------
# A3 — drop-recreate enum on dependent column
# ---------------------------------------------------------------------------

A3_LOOKAHEAD_STMTS = 3  # how many top-level stmts of upgrade() may sit between
# a <enum>.drop(...) and the matching <enum>.create(...) before we stop
# considering them a drop-recreate pair.


def _a3_resolve_var_to_enum_in_upgrade(upgrade_fn: ast.FunctionDef) -> dict[str, str]:
    """Variables assigned to ``postgresql.ENUM(..., name="X")`` or
    ``sa.Enum(..., name="X")`` inside the ``upgrade()`` function body."""
    out: dict[str, str] = {}
    for sub in ast.walk(upgrade_fn):
        if not (isinstance(sub, ast.Assign) and isinstance(sub.value, ast.Call)):
            continue
        enum_name = _enum_call_name(sub.value)
        if enum_name is None:
            continue
        for target in sub.targets:
            if isinstance(target, ast.Name):
                out[target.id] = enum_name
    return out


def _a3_enum_var_in_call(call: ast.Call) -> str | None:
    """For ``<var>.drop(...)`` / ``<var>.create(...)`` return ``<var>``."""
    func = call.func
    if not isinstance(func, ast.Attribute):
        return None
    if not isinstance(func.value, ast.Name):
        return None
    return func.value.id


def _a3_audit_one(
    path: Path,
    rev: str,
    scope: set[str],
    per_migration: dict[str, dict[tuple[str, str], str]],
) -> list[str]:
    """Detect: in upgrade() body, ``<var>.drop(...)`` followed within
    ``A3_LOOKAHEAD_STMTS`` top-level statements by ``<var>.create(...)`` —
    where ``<var>`` is a ``postgresql.ENUM(..., name="X")`` and some column
    of type ``"X"`` is already created by a predecessor migration.
    """
    src = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return []
    upgrade_fn = _func_node(tree, "upgrade")
    if upgrade_fn is None:
        return []

    var_to_enum = _a3_resolve_var_to_enum_in_upgrade(upgrade_fn)
    if not var_to_enum:
        return []

    # Top-level statements of upgrade(): for each, find the FIRST drop/create
    # call inside that statement (sufficient — drop/create are typically
    # single-line statements at top-level).
    stmts = list(upgrade_fn.body)

    def _first_var_call(stmt: ast.stmt, attr: str) -> tuple[str, int] | None:
        for sub in ast.walk(stmt):
            if not isinstance(sub, ast.Call):
                continue
            if not (isinstance(sub.func, ast.Attribute) and sub.func.attr == attr):
                continue
            var = _a3_enum_var_in_call(sub)
            if var is not None and var in var_to_enum:
                return var, sub.lineno
        return None

    def _find_create_after_drop_in_subtree(
        stmt: ast.stmt, var_name: str, drop_lineno: int
    ) -> int | None:
        """Within the SAME top-level statement that contains a drop call,
        find a ``<var_name>.create(...)`` whose ``lineno`` strictly exceeds
        ``drop_lineno`` (i.e., physically follows the drop in source order
        within e.g. one ``if dialect:`` block). Returns the create's lineno
        if found, else None.
        """
        for sub in ast.walk(stmt):
            if not isinstance(sub, ast.Call):
                continue
            func = sub.func
            if not (isinstance(func, ast.Attribute) and func.attr == "create"):
                continue
            if not (isinstance(func.value, ast.Name) and func.value.id == var_name):
                continue
            if sub.lineno > drop_lineno:
                return sub.lineno
        return None

    # Build enum → columns-of-that-type-from-predecessors index.
    # We use the cross-migration column type index here.
    dependent_cols_by_enum: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    for pred_rev in scope - {rev}:
        cols = per_migration.get(pred_rev, {})
        for (t, c), type_label in cols.items():
            if type_label.startswith("ENUM:"):
                dependent_cols_by_enum[type_label[5:]].append((pred_rev, t, c))

    rel = _safe_rel(path)
    violations: list[str] = []
    used_drop_idx: set[int] = set()  # avoid double-counting paired drops

    def _emit(drop_lineno: int, create_lineno: int, var: str) -> None:
        enum_name = var_to_enum[var]
        dependents = dependent_cols_by_enum.get(enum_name, [])
        if not dependents:
            # Drop-recreate without any dependent column — harmless, no A3
            # violation. (May still be a code smell, but iter-14 only blocks
            # the dependency-bearing form.)
            return
        dep_str = ", ".join(
            f"{r}/{t}.{c}" for r, t, c in sorted(dependents)[:5]
        )
        if len(dependents) > 5:
            dep_str += f", +{len(dependents) - 5} more"
        violations.append(
            f"{rel}:{drop_lineno}  drop-recreate of enum {enum_name!r} "
            f"via variable {var!r} (create at line {create_lineno}); "
            f"dependent columns exist in predecessors: [{dep_str}]. "
            "Fix: split this migration — add new values in-place with "
            "ALTER TYPE ... ADD VALUE IF NOT EXISTS '<v>' (under PG "
            "dialect gate), and move any data UPDATE referencing the new "
            "values into a follow-up <X>b_<topic>_data.py revision. "
            "Precedent: next55 → next55 + next55b split (PR #564)."
        )

    for i, stmt in enumerate(stmts):
        drop = _first_var_call(stmt, "drop")
        if drop is None or i in used_drop_idx:
            continue
        var, drop_lineno = drop
        # First check: same-top-level-statement drop+create (e.g. inside
        # one ``if dialect == 'postgresql':`` block). This is the natural
        # pattern an engineer would write and the original i+1 lookahead
        # missed it entirely.
        same_stmt_create = _find_create_after_drop_in_subtree(
            stmt, var, drop_lineno
        )
        if same_stmt_create is not None:
            _emit(drop_lineno, same_stmt_create, var)
            used_drop_idx.add(i)
            continue
        # Fallback: drop and create in separate top-level statements, within
        # A3_LOOKAHEAD_STMTS distance.
        for j in range(i + 1, min(i + 1 + A3_LOOKAHEAD_STMTS + 1, len(stmts))):
            create = _first_var_call(stmts[j], "create")
            if create is None:
                continue
            create_var, create_lineno = create
            if create_var != var:
                continue
            _emit(drop_lineno, create_lineno, var)
            used_drop_idx.add(i)
            break
    return violations


# ---------------------------------------------------------------------------
# A5 — unsafe use of newly-added enum value (iter-14)
# ---------------------------------------------------------------------------
#
# env.py wraps the whole ``alembic upgrade head`` in one outer async
# transaction; PG12+ refuses to use a newly-added enum value in the same tx
# where ``ALTER TYPE <name> ADD VALUE '<V>'`` ran. So if any revision in
# the upgrade chain adds ``'<V>'`` to enum ``<name>``, no revision (the
# adder itself or any descendant) may reference ``'<V>'`` from a SQL DML
# statement targeted at a column of type ``<name>``. iter-13 split next55
# under the mistaken belief that alembic enforces transaction-per-revision;
# CI run 26294051531 showed otherwise.
#
# Detection scope, on purpose narrow (see module docstring):
#   * ADD-VALUE side: ``op.execute("ALTER TYPE <enum> ADD VALUE [IF NOT
#     EXISTS] '<V>'")`` (case-insensitive) — collected per migration.
#   * USE side: ``op.execute("...")`` whose string literal contains an
#     ``UPDATE`` / ``INSERT`` / ``WHERE``-with-``=`` referencing a value
#     that matches an ADD-VALUE somewhere in (predecessor ∪ {self}) for an
#     enum whose corresponding column ``(table, col)`` is known to be of
#     that enum type. Arbitrary SQL string literals that don't resolve to
#     a known enum column are silently ignored — better to under-report
#     than to drown the signal in noise.


_ADD_VALUE_RE = re.compile(
    r"ALTER\s+TYPE\s+(\w+)\s+ADD\s+VALUE\s+(?:IF\s+NOT\s+EXISTS\s+)?"
    r"['\"](\w+)['\"]",
    re.IGNORECASE,
)

# UPDATE <t> ... SET <col> = '<v>'  (captures table, col, value)
_UPDATE_SET_RE = re.compile(
    r"UPDATE\s+(\w+)\b[^;]*?\bSET\s+(\w+)\s*=\s*['\"](\w+)['\"]",
    re.IGNORECASE,
)

# INSERT INTO <t> (... <col> ...) VALUES (... '<v>' ...) — too noisy to
# parse positionally; instead, catch the common form INSERT INTO <t> SET
# <col> = '<v>' (MySQL) plus the conservative INSERT INTO <t> (<col>)
# VALUES ('<v>') single-column case. Both rare in this codebase — kept
# narrow to avoid false positives. See module docstring.
_INSERT_SINGLE_COL_RE = re.compile(
    r"INSERT\s+INTO\s+(\w+)\s*\(\s*(\w+)\s*\)\s*VALUES\s*\(\s*['\"](\w+)['\"]\s*\)",
    re.IGNORECASE,
)

# WHERE <col> = '<v>' — paired with the surrounding statement's table is
# tricky and we don't need it for the known iter-14 regression class.
# Left out on purpose. (See module docstring on under-reporting trade-off.)


def _str_literal_iterable(node: ast.AST) -> list[str] | None:
    """If ``node`` is a tuple/list/set of string literals, return them.
    Else return None."""
    if not isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        return None
    out: list[str] = []
    for elt in node.elts:
        v = _str_const(elt)
        if v is None:
            return None
        out.append(v)
    return out


def _expand_fstring(
    node: ast.AST, var_bindings: dict[str, list[str]]
) -> list[str] | None:
    """Materialize all possible concrete strings from a ``JoinedStr`` /
    ``Constant`` AST node, given variable-name → possible-values bindings
    drawn from enclosing ``for x in (lit_a, lit_b):`` loops.

    Returns:
      * For an ``ast.Constant(str)`` → ``[that_str]``.
      * For an ``ast.JoinedStr``: list of every concrete realization
        (Cartesian product over all FormattedValue substitutions). All
        FormattedValue.value nodes must be simple ``ast.Name`` references
        to keys in ``var_bindings``; format spec / conversion ignored.
      * Else ``None``.
    """
    s = _str_const(node)
    if s is not None:
        return [s]
    if not isinstance(node, ast.JoinedStr):
        return None
    pieces: list[list[str]] = []
    for part in node.values:
        if isinstance(part, ast.Constant) and isinstance(part.value, str):
            pieces.append([part.value])
            continue
        if isinstance(part, ast.FormattedValue):
            inner = part.value
            if not isinstance(inner, ast.Name):
                return None
            if inner.id not in var_bindings:
                return None
            pieces.append(list(var_bindings[inner.id]))
            continue
        return None
    out: list[str] = [""]
    for piece in pieces:
        out = [prefix + p for prefix in out for p in piece]
    return out


def _enclosing_for_bindings(
    fn: ast.FunctionDef, target_node: ast.AST
) -> dict[str, list[str]]:
    """Walk ``fn`` once and return ``{var_name: [literal, ...]}`` for every
    ``for var in (lit_a, lit_b, ...):`` (or list/set) loop that physically
    encloses ``target_node`` (line-range containment over
    ``lineno``/``end_lineno``). Caller can then resolve f-string
    FormattedValues against these bindings.
    """
    out: dict[str, list[str]] = {}
    target_lineno = getattr(target_node, "lineno", None)
    if target_lineno is None:
        return out
    for sub in ast.walk(fn):
        if not isinstance(sub, ast.For):
            continue
        start = sub.lineno
        end = getattr(sub, "end_lineno", start)
        if not (start <= target_lineno <= end):
            continue
        if not isinstance(sub.target, ast.Name):
            continue
        lits = _str_literal_iterable(sub.iter)
        if lits is None:
            continue
        out[sub.target.id] = lits
    return out


def _a5_collect_added_values(tree: ast.Module) -> set[tuple[str, str]]:
    """Return ``{(enum_name, value)}`` pairs added via
    ``op.execute("ALTER TYPE ... ADD VALUE 'X'")`` in this migration's
    ``upgrade()``.

    Handles three SQL-source shapes (in order of frequency in this repo):
      1. Literal string: ``op.execute("ALTER TYPE e ADD VALUE 'X'")``.
      2. f-string inside a for-loop over a literal tuple/list of values:
         ``for v in ("X", "Y"): op.execute(f"... ADD VALUE '{v}'")``.
      3. f-string at module scope with no enclosing loop is treated as
         a single concrete string (FormattedValue parts that don't resolve
         to a known binding cause the whole call to be skipped — under-
         report rather than over-report).
    """
    upgrade_fn = _func_node(tree, "upgrade")
    if upgrade_fn is None:
        return set()
    out: set[tuple[str, str]] = set()
    for node in ast.walk(upgrade_fn):
        if not isinstance(node, ast.Call):
            continue
        if not _is_op_call(node, "execute"):
            continue
        if not node.args:
            continue
        arg = node.args[0]
        bindings = _enclosing_for_bindings(upgrade_fn, node)
        candidates = _expand_fstring(arg, bindings)
        if candidates is None:
            continue
        for sql in candidates:
            for m in _ADD_VALUE_RE.finditer(sql):
                out.add((m.group(1), m.group(2)))
    return out


def _a5_iter_used_values(
    tree: ast.Module,
) -> list[tuple[str, str, str, int]]:
    """Return ``[(table, col, value, lineno), ...]`` of literal enum-value
    references inside ``op.execute("UPDATE ... SET <col> = '<V>'")`` or
    ``op.execute("INSERT INTO <t> (<col>) VALUES ('<V>')")`` statements in
    this migration's ``upgrade()``.

    Both literal strings and ``f"..."`` strings are supported; in the
    latter case the FormattedValue must resolve to an ``ast.Name`` whose
    binding comes from an enclosing ``for var in (lit, lit, ...):`` loop.

    These are *candidate* references. Whether they're actually an enum
    value (vs. an arbitrary string literal that happens to match) is
    decided by the caller using the cross-migration column-type index.
    """
    upgrade_fn = _func_node(tree, "upgrade")
    if upgrade_fn is None:
        return []
    out: list[tuple[str, str, str, int]] = []
    for node in ast.walk(upgrade_fn):
        if not isinstance(node, ast.Call):
            continue
        if not _is_op_call(node, "execute"):
            continue
        if not node.args:
            continue
        arg = node.args[0]
        bindings = _enclosing_for_bindings(upgrade_fn, node)
        candidates = _expand_fstring(arg, bindings)
        if candidates is None:
            continue
        for sql in candidates:
            for m in _UPDATE_SET_RE.finditer(sql):
                out.append((m.group(1), m.group(2), m.group(3), node.lineno))
            for m in _INSERT_SINGLE_COL_RE.finditer(sql):
                out.append((m.group(1), m.group(2), m.group(3), node.lineno))
    return out


def _a5_audit_one(
    path: Path,
    rev: str,
    scope: set[str],
    per_migration: dict[str, dict[tuple[str, str], str]],
    added_values_by_rev: dict[str, set[tuple[str, str]]],
) -> list[str]:
    """Flag every ``op.execute(...)`` in this migration whose SQL references
    a literal enum-value matching an ``ALTER TYPE ... ADD VALUE`` performed
    by any revision in ``scope`` (which is ``predecessors ∪ {self}``).
    """
    src = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return []
    used = _a5_iter_used_values(tree)
    if not used:
        return []

    # Build the union of (enum_name, value) added by anyone in scope,
    # plus a reverse index: value → adder_revs (for nicer messages).
    in_scope_added: dict[tuple[str, str], list[str]] = defaultdict(list)
    for r in scope:
        for pair in added_values_by_rev.get(r, set()):
            in_scope_added[pair].append(r)
    if not in_scope_added:
        return []

    rel = _safe_rel(path)
    out: list[str] = []
    for table, col, value, lineno in used:
        # Resolve (table, col) → enum_name using the cross-migration index.
        col_type = _lookup_column_type(table, col, scope, per_migration)
        if not col_type.startswith("ENUM:"):
            # Not a known enum column — could be any string column.
            # Skip to avoid the regex matching arbitrary SQL literals.
            continue
        enum_name = col_type[5:]
        if (enum_name, value) not in in_scope_added:
            continue
        adders = sorted(in_scope_added[(enum_name, value)])
        adder_str = ", ".join(adders[:3])
        if len(adders) > 3:
            adder_str += f", +{len(adders) - 3} more"
        if rev in adders:
            same_rev_note = " (same revision)"
        else:
            same_rev_note = ""
        out.append(
            f"{rel}:{lineno}  op.execute SQL references value {value!r} of "
            f"enum {enum_name!r} on column {table}.{col}; that value was "
            f"added by ALTER TYPE in revision(s) [{adder_str}]{same_rev_note}. "
            "env.py wraps `alembic upgrade head` in one outer transaction, so "
            "PG12+'s UnsafeNewEnumValueUsageError applies across all "
            "revisions in the chain — splitting into separate revisions does "
            "not help. Fix recommendations (in priority order): "
            "(a) remove the data UPDATE entirely if existing rows have valid "
            "alternative values under the extended enum (often true since "
            "ALTER TYPE ADD VALUE preserves existing column values); "
            "(b) move the data migration to an app-level startup hook or one-"
            "shot CLI command run AFTER `alembic upgrade head`; "
            "(c) refactor env.py to not wrap migrations in an outer transaction "
            "(invasive, out of scope for normal migration work). "
            "Precedent: iter-14 commit c66d4f1 (PR #564) removed the lossy "
            "UPDATE in next55b."
        )
    return out


# ---------------------------------------------------------------------------
# A4 — cross-branch dependencies (delegate to existing test)
# ---------------------------------------------------------------------------


def _a4_audit() -> list[str]:
    """Delegate to the narrow-guard analyzer in
    ``test_migrations_cross_branch_deps``.

    That implementation has ~1k lines of tuned FP-filtering for the local
    helper-inlining, batch-alter-table, for-loop create-table, and rename
    propagation patterns in this codebase. Re-porting it would invite drift.
    """
    migrations = _xbranch_collect_all()
    raw = _xbranch_audit(migrations)
    out: list[str] = []
    for v in raw:
        target = v.table if v.column is None else f"{v.table}.{v.column}"
        out.append(
            f"{v.file}  rev={v.migration}  ref={target} — {v.why}"
        )
    return out


# ---------------------------------------------------------------------------
# Top-level orchestration
# ---------------------------------------------------------------------------


def _build_added_values_index(
    path_of_rev: dict[str, Path],
) -> dict[str, set[tuple[str, str]]]:
    """Pre-pass for A5: for every migration, collect the ``{(enum_name,
    value)}`` pairs it adds via ``ALTER TYPE ADD VALUE``. Computed once
    and shared across all per-migration A5 calls.
    """
    out: dict[str, set[tuple[str, str]]] = {}
    for r, path in path_of_rev.items():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            out[r] = set()
            continue
        out[r] = _a5_collect_added_values(tree)
    return out


def find_violations() -> dict[str, list[str]]:
    """Run all 5 antipattern visitors over every migration in
    ``backend/app/migrations/versions``. Returns dict keyed by antipattern
    class (``A1`` / ``A2`` / ``A3`` / ``A4`` / ``A5``), values are
    human-readable violation strings (file:line + cause + recommendation).
    """
    out: dict[str, list[str]] = {
        "A1": [],
        "A2": [],
        "A3": [],
        "A4": [],
        "A5": [],
    }

    per_migration, predecessors, _rev_of_file, path_of_rev = _build_column_type_index()
    added_values_by_rev = _build_added_values_index(path_of_rev)

    # A1: doesn't need the DAG index.
    for path in sorted(MIGRATIONS_DIR.glob("*.py")):
        out["A1"].extend(_a1_audit_one(path))

    # A2 + A3 + A5: per-migration with scope = {self} ∪ predecessors.
    for rev, path in sorted(path_of_rev.items()):
        scope = predecessors.get(rev, set()) | {rev}
        out["A2"].extend(_a2_audit_one(path, rev, scope, per_migration))
        out["A3"].extend(_a3_audit_one(path, rev, scope, per_migration))
        out["A5"].extend(
            _a5_audit_one(path, rev, scope, per_migration, added_values_by_rev)
        )

    # A4: whole-repo DAG analyzer.
    out["A4"].extend(_a4_audit())

    return out


# ---------------------------------------------------------------------------
# pytest entry points
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def violations() -> dict[str, list[str]]:
    return find_violations()


def test_a1_no_enum_double_create(violations: dict[str, list[str]]) -> None:
    assert violations["A1"] == [], "A1 violations:\n" + "\n".join(violations["A1"])


def test_a2_no_gin_on_non_jsonb(violations: dict[str, list[str]]) -> None:
    assert violations["A2"] == [], "A2 violations:\n" + "\n".join(violations["A2"])


def test_a3_no_enum_drop_recreate_on_dependent_column(
    violations: dict[str, list[str]],
) -> None:
    assert violations["A3"] == [], "A3 violations:\n" + "\n".join(violations["A3"])


def test_a4_no_missing_cross_branch_depends_on(
    violations: dict[str, list[str]],
) -> None:
    assert violations["A4"] == [], "A4 violations:\n" + "\n".join(violations["A4"])


def test_a5_no_unsafe_new_enum_value_usage(
    violations: dict[str, list[str]],
) -> None:
    assert violations["A5"] == [], "A5 violations:\n" + "\n".join(violations["A5"])


def test_migrations_dir_exists() -> None:
    assert MIGRATIONS_DIR.is_dir(), f"missing migrations dir: {MIGRATIONS_DIR}"
    assert any(MIGRATIONS_DIR.glob("*.py")), "no *.py migrations found"


# ---------------------------------------------------------------------------
# Synthetic-violation harness — prove each visitor fires on its target pattern
# ---------------------------------------------------------------------------
#
# The "real-repo" pytests above assert each visitor returns 0 violations on
# the CURRENT migrations directory. They cannot, on their own, prove the
# visitor would FIRE on a known-bad migration — a silently-broken visitor
# (e.g., a regex that never matches) would pass them just as well as a
# correct visitor.
#
# This harness closes that gap. Each synthetic snippet is a self-contained
# migration source string with exactly one antipattern. We write it to a
# tmp_path file, run the matching visitor in isolation, and assert it emits
# at least one violation message containing a class-specific substring.
#
# When you add a new antipattern class, ALSO add a synthetic snippet here.
# When you tighten a visitor's precision, the synthetic test guards against
# accidentally tightening it past the regression class it's supposed to
# catch.


SYNTHETIC_A1 = '''
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "synthetic_a1"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    my_enum = postgresql.ENUM("X", "Y", name="my_enum_t", create_type=True)
    my_enum.create(op.get_bind(), checkfirst=True)
    op.add_column("t", sa.Column("c", sa.Enum("X", "Y", name="my_enum_t"), nullable=True))


def downgrade() -> None:
    pass
'''


SYNTHETIC_A2 = '''
import sqlalchemy as sa
from alembic import op

revision = "synthetic_a2"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("t", sa.Column("tags", sa.JSON(), nullable=False))
    op.create_index("ix_t_tags_gin", "t", ["tags"], postgresql_using="gin")


def downgrade() -> None:
    pass
'''


SYNTHETIC_A3_PREDECESSOR = '''
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "synthetic_a3_pred"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    some_enum = postgresql.ENUM("X", "Y", name="some_enum", create_type=False)
    some_enum.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "some_table",
        sa.Column("col", some_enum, nullable=False),
    )


def downgrade() -> None:
    pass
'''


# A3 with drop+create in the SAME top-level statement (one `if dialect:`
# block). The pre-fix visitor's i+1 lookahead missed this; with the
# Change-2 fix it must fire.
SYNTHETIC_A3 = '''
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "synthetic_a3"
down_revision = "synthetic_a3_pred"
branch_labels = None
depends_on = None


def upgrade() -> None:
    some_enum = postgresql.ENUM("X", "Y", "Z", name="some_enum", create_type=False)
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        some_enum.drop(bind, checkfirst=False)
        some_enum.create(bind, checkfirst=False)


def downgrade() -> None:
    pass
'''


# A5 — ALTER TYPE ADD VALUE and UPDATE in the same revision.
# Predecessor declares the column so the (table, col) → enum_name lookup
# succeeds for the UPDATE's resolution.
SYNTHETIC_A5_PREDECESSOR = '''
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "synthetic_a5_pred"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "some_table",
        sa.Column("col", sa.Enum("OLD1", "OLD2", name="some_enum"), nullable=False),
    )


def downgrade() -> None:
    pass
'''


SYNTHETIC_A5 = '''
import sqlalchemy as sa
from alembic import op

revision = "synthetic_a5"
down_revision = "synthetic_a5_pred"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE some_enum ADD VALUE IF NOT EXISTS 'NEWVAL'")
    op.execute("UPDATE some_table SET col = 'NEWVAL'")


def downgrade() -> None:
    pass
'''


def _parse(src: str) -> ast.Module:
    return ast.parse(src)


def test_a1_visitor_fires_on_synthetic(tmp_path) -> None:
    """A1 visitor must flag enum-double-create on the canonical bad pattern."""
    p = tmp_path / "synth_a1.py"
    p.write_text(SYNTHETIC_A1, encoding="utf-8")
    violations = _a1_audit_one(p)
    assert violations, "A1 visitor should fire on SYNTHETIC_A1 — none returned"
    assert any("create_type=False" in v for v in violations), (
        f"A1 message should mention 'create_type=False'; got: {violations}"
    )


def test_a2_visitor_fires_on_synthetic(tmp_path) -> None:
    """A2 visitor must flag GIN-on-JSON column."""
    p = tmp_path / "synth_a2.py"
    p.write_text(SYNTHETIC_A2, encoding="utf-8")
    # Build a self-contained per-migration index so the lookup resolves.
    rev = "synthetic_a2"
    per_migration = {rev: _columns_created_by_migration(_parse(SYNTHETIC_A2))}
    scope = {rev}
    violations = _a2_audit_one(p, rev, scope, per_migration)
    assert violations, "A2 visitor should fire on SYNTHETIC_A2 — none returned"
    assert any("GIN" in v or "gin" in v for v in violations), (
        f"A2 message should mention 'GIN'; got: {violations}"
    )


def test_a3_visitor_fires_on_synthetic_with_predecessor(tmp_path) -> None:
    """A3 visitor must flag drop-recreate inside a single ``if dialect:`` block
    when a predecessor declares a column of the enum type.

    This synthetic is the regression test for Change 2 (same-statement edge
    case). With the pre-fix visitor's i+1 lookahead, this would silently
    pass (no violation); with the Change-2 fix, it must fire.
    """
    # Write predecessor and child to a tmp dir.
    pred_path = tmp_path / "synth_a3_pred.py"
    pred_path.write_text(SYNTHETIC_A3_PREDECESSOR, encoding="utf-8")
    child_path = tmp_path / "synth_a3.py"
    child_path.write_text(SYNTHETIC_A3, encoding="utf-8")

    pred_rev = "synthetic_a3_pred"
    child_rev = "synthetic_a3"
    per_migration = {
        pred_rev: _columns_created_by_migration(_parse(SYNTHETIC_A3_PREDECESSOR)),
        child_rev: _columns_created_by_migration(_parse(SYNTHETIC_A3)),
    }
    # Scope = predecessor ∪ {self} as in find_violations.
    scope = {pred_rev, child_rev}
    violations = _a3_audit_one(child_path, child_rev, scope, per_migration)
    assert violations, (
        "A3 visitor should fire on SYNTHETIC_A3 with predecessor — "
        "this is the Change-2 same-statement regression test"
    )
    assert any("some_enum" in v for v in violations), (
        f"A3 message should mention enum name 'some_enum'; got: {violations}"
    )
    assert any("ALTER TYPE" in v for v in violations), (
        f"A3 message should reference 'ALTER TYPE' fix; got: {violations}"
    )


def test_a5_visitor_fires_on_synthetic_with_predecessor(tmp_path) -> None:
    """A5 visitor must flag ``ALTER TYPE ADD VALUE 'X'`` followed by
    ``UPDATE ... SET col = 'X'`` referencing a column of the same enum.

    Both same-revision (synthetic case here) and cross-revision (the real
    next55 → next55b case, regression-tested separately by toggling the
    next55b file) must be detected.
    """
    pred_path = tmp_path / "synth_a5_pred.py"
    pred_path.write_text(SYNTHETIC_A5_PREDECESSOR, encoding="utf-8")
    child_path = tmp_path / "synth_a5.py"
    child_path.write_text(SYNTHETIC_A5, encoding="utf-8")

    pred_rev = "synthetic_a5_pred"
    child_rev = "synthetic_a5"
    per_migration = {
        pred_rev: _columns_created_by_migration(_parse(SYNTHETIC_A5_PREDECESSOR)),
        child_rev: _columns_created_by_migration(_parse(SYNTHETIC_A5)),
    }
    added_values_by_rev = {
        pred_rev: _a5_collect_added_values(_parse(SYNTHETIC_A5_PREDECESSOR)),
        child_rev: _a5_collect_added_values(_parse(SYNTHETIC_A5)),
    }
    scope = {pred_rev, child_rev}
    violations = _a5_audit_one(
        child_path, child_rev, scope, per_migration, added_values_by_rev
    )
    assert violations, (
        "A5 visitor should fire on SYNTHETIC_A5 — same-revision "
        "ALTER TYPE ADD VALUE + UPDATE"
    )
    assert any("NEWVAL" in v for v in violations), (
        f"A5 message should reference the added value 'NEWVAL'; got: {violations}"
    )
    assert any("UnsafeNewEnumValueUsageError" in v or "outer transaction" in v
               for v in violations), (
        f"A5 message should reference the outer-tx mechanism; got: {violations}"
    )


# ---------------------------------------------------------------------------
# Direct invocation (Windows+Py3.13 conftest hang workaround)
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    result = find_violations()
    total = sum(len(v) for v in result.values())
    if total == 0:
        print("OK — no migration antipattern violations found.")
        print("  A1 (enum double-create):                       0")
        print("  A2 (GIN on non-JSONB):                         0")
        print("  A3 (drop-recreate enum on dependent column):   0")
        print("  A4 (cross-branch dep missing depends_on):      0")
        print("  A5 (unsafe use of newly-added enum value):     0")
        sys.exit(0)
    print(f"VIOLATIONS: {total} total")
    for klass, lines in result.items():
        print(f"\n  {klass} — {len(lines)} violation(s):")
        for line in lines:
            print(f"    {line}")
    sys.exit(1)
