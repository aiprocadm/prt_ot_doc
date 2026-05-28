"""Server-default parity audit. Pure AST, no app imports.

Finds model columns declared ``nullable=False`` with a Python-side
``default=<literal or enum attribute>`` whose migration form is
``nullable=False`` **without** a matching ``server_default``.

Why this matters: Python's ``default=`` only fires on ORM inserts. Raw
SQL paths (restore-drill SQL dumps, perf-baseline ``COPY`` loads, manual
ops fixes, alembic ``op.execute("INSERT ...")``) hit ``NOT NULL`` if the
column has no DB-side default. iter-32 fixed this for
``ppeissue.quantity`` by adding ``server_default="1"`` to its
``add_column`` call; this audit finds the rest.

Companion to:
  - ``column_drift_lite.py`` (column presence drift, flavor (b))
  - ``version_column_drift.py`` (version-column mixin drift)

Scope rules:
  - **In-scope model column**: ``mapped_column(..., nullable=False, default=<literal or enum attr>)``.
    Literal forms: ``ast.Constant`` (int/str/bool/None) and ``ast.Attribute``
    chains like ``RecordStatus.DRAFT`` (enum literal).
  - **Out of scope**: callable defaults (``default=uuid.uuid4``,
    ``default=datetime.utcnow``) — can't translate to a DB-side default.
  - **Out of scope**: ``nullable=True`` (Python default is sugar; no DB
    invariant broken).
  - **Out of scope**: columns absent entirely from migrations — that's
    ``column_drift_lite``'s territory.

Usage:
    py -3 scripts/audit/server_default_parity.py
    py -3 scripts/audit/server_default_parity.py --verbose
"""

from __future__ import annotations

import argparse
import ast
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MODELS_FILE = REPO_ROOT / "backend" / "app" / "models" / "models.py"
MIGRATIONS_DIR = REPO_ROOT / "backend" / "app" / "migrations" / "versions"


def _is_mapped_column_call(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name) and func.id == "mapped_column":
        return True
    if isinstance(func, ast.Attribute) and func.attr == "mapped_column":
        return True
    return False


def _literal_default_repr(value: ast.AST) -> str | None:
    """Return printable repr of an in-scope default, or None if out of scope.

    Heuristic for distinguishing enum literals (in scope) from callable
    references (out of scope) when both are ``ast.Attribute``: enum members
    follow PEP 8 UPPER_CASE convention (``RecordStatus.DRAFT``), callables
    are lower_case (``uuid.uuid4``, ``date.today``). We accept only the
    UPPER_CASE form.
    """
    if isinstance(value, ast.Constant):
        return repr(value.value)
    if isinstance(value, ast.Attribute):
        attr_name = value.attr
        if not attr_name or not attr_name[0].isupper():
            return None
        try:
            return ast.unparse(value)
        except Exception:
            return None
    return None


def _table_for_class(cls_node: ast.ClassDef) -> str:
    """Return ``__tablename__`` if set, else SQLAlchemy's default (lowercased class name)."""
    for c in cls_node.body:
        if isinstance(c, ast.Assign):
            for tgt in c.targets:
                if isinstance(tgt, ast.Name) and tgt.id == "__tablename__":
                    if isinstance(c.value, ast.Constant) and isinstance(c.value.value, str):
                        return c.value.value
    return cls_node.name.lower()


def scan_model_default_candidates(model_path: Path) -> dict[tuple[str, str], dict[str, str]]:
    """Find all ``(table, column) -> {default_repr}`` candidates in a models file.

    Returns only in-scope rows: ``nullable=False`` + literal/enum default.
    """
    tree = ast.parse(model_path.read_text(encoding="utf-8"))
    out: dict[tuple[str, str], dict[str, str]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        table = _table_for_class(node)
        for member in node.body:
            if not isinstance(member, ast.AnnAssign) or not isinstance(member.target, ast.Name):
                continue
            if not _is_mapped_column_call(member.value):
                continue
            mc = member.value
            assert isinstance(mc, ast.Call)
            nullable: bool | None = None
            default_repr: str | None = None
            for kw in mc.keywords:
                if kw.arg == "nullable" and isinstance(kw.value, ast.Constant):
                    nullable = kw.value.value
                elif kw.arg == "default":
                    default_repr = _literal_default_repr(kw.value)
            if nullable is False and default_repr is not None:
                out[(table, member.target.id)] = {"default_repr": default_repr}
    return out


def _column_kwargs(call: ast.Call) -> dict[str, ast.AST]:
    return {kw.arg: kw.value for kw in call.keywords if kw.arg}


def _sa_column_calls_in(fn_or_module: ast.AST) -> list[ast.Call]:
    """All ``sa.Column(...)`` / ``Column(...)`` calls anywhere under fn_or_module."""
    found: list[ast.Call] = []
    for node in ast.walk(fn_or_module):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "Column":
            found.append(node)
        elif isinstance(func, ast.Name) and func.id == "Column":
            found.append(node)
    return found


def _column_name_and_create_table(call: ast.Call) -> tuple[str | None, ast.AST | None]:
    """For an op.create_table(...) call, return (table_name, call_node) if literal."""
    if not isinstance(call.func, ast.Attribute) or call.func.attr != "create_table":
        return None, None
    if not call.args or not isinstance(call.args[0], ast.Constant):
        return None, None
    if not isinstance(call.args[0].value, str):
        return None, None
    return call.args[0].value, call


def _add_column_target(call: ast.Call) -> tuple[str | None, ast.Call | None]:
    if not isinstance(call.func, ast.Attribute) or call.func.attr != "add_column":
        return None, None
    if len(call.args) < 2 or not isinstance(call.args[0], ast.Constant):
        return None, None
    if not isinstance(call.args[0].value, str):
        return None, None
    if not isinstance(call.args[1], ast.Call):
        return None, None
    return call.args[0].value, call.args[1]


def scan_migration_columns_with_defaults(
    migration_paths: list[Path],
) -> dict[str, dict[str, dict[str, bool]]]:
    """Return ``{table: {column: {has_server_default: bool}}}``.

    A column's presence is recorded the first time it's seen in a migration;
    once any migration declares ``server_default`` for it, the flag stays True.
    """
    out: dict[str, dict[str, dict[str, bool]]] = defaultdict(lambda: defaultdict(lambda: {"has_server_default": False}))

    for path in migration_paths:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue

            # create_table form
            tbl, ct_call = _column_name_and_create_table(node)
            if tbl is not None and ct_call is not None:
                for col_call in _sa_column_calls_in(ct_call):
                    if not col_call.args or not isinstance(col_call.args[0], ast.Constant):
                        continue
                    col_name = col_call.args[0].value
                    if not isinstance(col_name, str):
                        continue
                    has_sd = "server_default" in _column_kwargs(col_call)
                    cur = out[tbl][col_name]
                    if has_sd:
                        cur["has_server_default"] = True
                    else:
                        cur.setdefault("has_server_default", False)
                continue

            # add_column form
            tbl, col_call = _add_column_target(node)
            if tbl is not None and col_call is not None:
                if not col_call.args or not isinstance(col_call.args[0], ast.Constant):
                    continue
                col_name = col_call.args[0].value
                if not isinstance(col_name, str):
                    continue
                has_sd = "server_default" in _column_kwargs(col_call)
                cur = out[tbl][col_name]
                if has_sd:
                    cur["has_server_default"] = True
                else:
                    cur.setdefault("has_server_default", False)

    # Convert defaultdicts to plain dicts for cleaner test asserts.
    return {tbl: dict(cols) for tbl, cols in out.items()}


def detect_drift(
    model_path: Path, migration_paths: list[Path]
) -> dict[tuple[str, str], dict[str, str]]:
    """Return ``{(table, col): {default_repr}}`` for cols with parity drift."""
    model_candidates = scan_model_default_candidates(model_path)
    migration_info = scan_migration_columns_with_defaults(migration_paths)
    drift: dict[tuple[str, str], dict[str, str]] = {}
    for (table, col), meta in model_candidates.items():
        table_info = migration_info.get(table, {})
        col_info = table_info.get(col)
        if col_info is None:
            # column absent from migrations — column_drift_lite's domain
            continue
        if not col_info.get("has_server_default", False):
            drift[(table, col)] = meta
    return drift


def run() -> dict[tuple[str, str], dict[str, str]]:
    """Run audit against the real repo. Returns drift dict."""
    migration_paths = sorted(MIGRATIONS_DIR.glob("*.py"))
    return detect_drift(MODELS_FILE, migration_paths)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verbose", action="store_true", help="show per-table breakdown")
    args = parser.parse_args(argv)

    drift = run()
    by_table: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for (table, col), meta in drift.items():
        by_table[table].append((col, meta["default_repr"]))

    print(f"Model default-without-server_default candidates: {len(drift)} cols / {len(by_table)} tables")
    if args.verbose or len(drift) <= 80:
        for table in sorted(by_table):
            cols = sorted(by_table[table])
            print(f"  {table}  ({len(cols)} col{'s' if len(cols) != 1 else ''})")
            for col, dv in cols:
                print(f"    {col} = {dv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
