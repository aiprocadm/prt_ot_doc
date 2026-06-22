"""Minimal audit: which tables inherit `version` from mixin but lack it in migrations.

Bypasses the heavy `app.db.base` import chain that hangs on Win+Py3.13.
Pure AST analysis of models.py + migrations/versions/*.py.

**v2 (Session 79 fix)**: now detects helper functions that wrap
``op.create_table`` — e.g. ``_create_table("training_modules", ...)`` and
``_create_soft_table("briefing_templates", ...)`` in
``20260317_next46_training_briefings_offline.py``. The v1 implementation
only matched direct ``op.create_table`` literals, producing critical
false-positives that caused iter-30 PR #600 (briefing-cohort) to be a
duplicate-creation migration. See [[orm-migration-drift-classes]] for
the broader drift-class taxonomy.

Helper detection mirrors ``scripts/audit/check_orm_migration_drift.py``
(``_table_creating_helpers``): any module-local function that contains
an ``op.create_table`` call qualifies as a wrapper, and subsequent
calls ``<helper>("<tablename>", ...)`` inside ``upgrade()`` are credited
as creating the table.

**v3 (Session 80 fix)**: now resolves loop-variable tablenames for
``op.add_column``. iter-29's retrofit migration uses
``for table in _TABLES: op.add_column(table, sa.Column("version", ...))``
where ``_TABLES: tuple[str, ...] = (...)`` is a module-level constant.
v2 silently dropped these calls (``tname_arg`` is ``ast.Name``, not
``ast.Constant``), leaving the 8 retrofitted tables uncredited even after
the migration shipped — breaking closed-loop drift-count verification.

Loop resolution is intentionally narrow: only constant string sequences
declared at module level (``_NAME = (...)`` / ``_NAME: type = (...)``)
or inline (``for t in ("a", "b"):``) qualify. Function calls
(``for t in get_tables():``) and other unresolved iterables fall through
to the original "no credit" behavior. ``create_table`` loop-handling is
deliberately out of scope — no existing migration uses that pattern, and
expanding scope would risk regressing the v2 helper-detection path.

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


def _all_functions(tree: ast.Module) -> dict[str, ast.FunctionDef]:
    return {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}


def _table_creating_helpers(functions: dict[str, ast.FunctionDef]) -> set[str]:
    """Module-local helpers that ultimately call op.create_table.

    Mirrors check_orm_migration_drift.py:_table_creating_helpers but
    simpler — we only need helper names, not their extra columns
    (this audit only cares about "did this table get created at all",
    not the column list).
    """
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
    """Map module-level constant string sequences.

    Matches both ``_NAME = ("a", "b")`` (``ast.Assign``) and the typed form
    ``_NAME: tuple[str, ...] = ("a", "b")`` (``ast.AnnAssign``) — the latter
    is what iter-29's migration uses for ``_TABLES``. Only sequences whose
    elements are *all* string literals are included.
    """
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
    """Resolve a ``for`` loop's ``iter`` to a list of constant strings.

    Returns ``None`` when the iterable can't be statically resolved
    (function calls, generator expressions, etc.) — caller treats that as
    "no credit", same as the v2 path for an unrecognised tablename arg.
    """
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
    """Build ``{id(child): parent}`` for every descendant of ``root``."""
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
    """Loop-variable bindings in scope for ``node``.

    Walks ancestors via ``parents``; each enclosing ``ast.For`` with a
    ``Name`` target and a resolvable ``iter`` contributes one binding.
    Innermost binding wins on shadowing (we walk outward).
    """
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


def _helper_creates_version(functions: dict[str, ast.FunctionDef], helper_name: str) -> bool:
    """True if the helper's body has a literal sa.Column("version", ...).

    For e.g. next46's ``_create_table``/``_create_soft_table`` which both
    inject ``_base_columns()`` (which includes ``version``), we need to
    follow same-module helper calls too.
    """
    visited: set[str] = set()

    def _walk(name: str) -> bool:
        if name in visited:
            return False
        visited.add(name)
        func = functions.get(name)
        if func is None:
            return False
        for node in ast.walk(func):
            if not isinstance(node, ast.Call):
                continue
            f = node.func
            # Direct sa.Column("version", ...) literal.
            if (
                isinstance(f, ast.Attribute)
                and f.attr == "Column"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and node.args[0].value == "version"
            ):
                return True
            # Recurse into other helpers called from this helper.
            if isinstance(f, ast.Name) and f.id in functions and f.id != name:
                if _walk(f.id):
                    return True
        return False

    return _walk(helper_name)


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
                and any(isinstance(t, ast.Name) and t.id == "__tablename__" for t in sub.targets)
                and isinstance(sub.value, ast.Constant)
                and isinstance(sub.value.value, str)
            ):
                tablename = sub.value.value
        result[tablename] = node.name
    return result


def _migration_creates_version(path: Path) -> set[str]:
    """Return set of tablenames where migration's upgrade() creates a `version` column.

    Detects both direct ``op.create_table("t", sa.Column("version", ...))``
    and helper-wrapped ``_create_table("t", ...)`` where the helper's body
    (or transitively-called same-module helpers) declares the column.
    """
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src, filename=str(path))
    upgrade_fn = None
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "upgrade":
            upgrade_fn = node
            break
    if upgrade_fn is None:
        return set()
    functions = _all_functions(tree)
    helpers = _table_creating_helpers(functions)
    helpers_creating_version = {h for h in helpers if _helper_creates_version(functions, h)}
    tables_with_version: set[str] = set()
    for node in ast.walk(upgrade_fn):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        # Direct op.create_table("foo", sa.Column("version", ...), ...)
        is_create = (isinstance(func, ast.Attribute) and func.attr == "create_table") or (
            isinstance(func, ast.Name) and func.id == "create_table"
        )
        if is_create and node.args:
            first = node.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                tablename = first.value
                for col_call in node.args[1:]:
                    if not isinstance(col_call, ast.Call):
                        continue
                    cf = col_call.func
                    ends_column = (isinstance(cf, ast.Attribute) and cf.attr == "Column") or (
                        isinstance(cf, ast.Name) and cf.id == "Column"
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
        # Helper-wrapped: _create_table("foo", ...) where helper injects version.
        if (
            isinstance(func, ast.Name)
            and func.id in helpers_creating_version
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            tables_with_version.add(node.args[0].value)
    # Also scan op.add_column("foo", sa.Column("version", ...)) and batch variants.
    # v3 (Session 79 known-gap fix): credit calls inside a ``for t in _TABLES``
    # loop where ``_TABLES`` is a module-level constant string sequence. iter-29
    # uses this pattern; v2 silently dropped such calls because ``tname_arg``
    # was ``ast.Name``, not ``ast.Constant``.
    module_constants = _module_string_seqs(tree)
    parents = _parent_map(upgrade_fn)
    for node in ast.walk(upgrade_fn):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        is_add = (isinstance(func, ast.Attribute) and func.attr == "add_column") or (
            isinstance(func, ast.Name) and func.id == "add_column"
        )
        if not is_add or len(node.args) < 2:
            continue
        tname_arg = node.args[0]
        col_arg = node.args[1]
        if isinstance(tname_arg, ast.Constant) and isinstance(tname_arg.value, str):
            tablename_candidates: list[str] = [tname_arg.value]
        elif isinstance(tname_arg, ast.Name):
            loop_bindings = _enclosing_for_bindings(node, parents, module_constants)
            tablename_candidates = loop_bindings.get(tname_arg.id, [])
        else:
            # batch.add_column has 1 arg (column only); With-ancestor branch handles it.
            continue
        if not tablename_candidates:
            continue
        if (
            isinstance(col_arg, ast.Call)
            and col_arg.args
            and isinstance(col_arg.args[0], ast.Constant)
            and col_arg.args[0].value == "version"
        ):
            tables_with_version.update(tablename_candidates)
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
    """Tables that *any* op creates (used to detect critical / absent tables).

    Includes both direct ``op.create_table("t", ...)`` and helper-wrapped
    ``<helper>("t", ...)`` calls where the helper transitively calls
    ``op.create_table``. Without helper detection, this audit produces
    critical false-positives — e.g. next46's _create_table/_create_soft_table
    wrappers create ~20 tables that direct-match would miss.
    """
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src, filename=str(path))
    upgrade_fn = None
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "upgrade":
            upgrade_fn = node
    if upgrade_fn is None:
        return set()
    functions = _all_functions(tree)
    helpers = _table_creating_helpers(functions)
    tables: set[str] = set()
    for node in ast.walk(upgrade_fn):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        # Direct op.create_table("t", ...).
        if (isinstance(func, ast.Attribute) and func.attr == "create_table") or (
            isinstance(func, ast.Name) and func.id == "create_table"
        ):
            if (
                node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                tables.add(node.args[0].value)
        # Helper-wrapped: <helper>("t", ...).
        if (
            isinstance(func, ast.Name)
            and func.id in helpers
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
