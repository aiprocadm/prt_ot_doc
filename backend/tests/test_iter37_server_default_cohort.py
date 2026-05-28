"""Pin tests for iter-37 server_default parity cohort migration (Subset A+B).

Closes the safe-to-ship subset of server_default drift discovered by
``scripts/audit/server_default_parity.py`` (Session 83 / iter-36):

  * **Subset A** — int/bool literal defaults (15 cols).
  * **Subset B** — short string literal defaults (4 cols).
  * **Subset C** — enum-typed defaults (32 cols) + ``tenant.kind``
    (string literal but ``Enum`` column type) — deferred. They need
    per-dialect ``server_default`` SQL (PG ``::enum_name`` cast) and a
    decision on SQLite behavior. Out of scope for iter-37.

Same operational impact as iter-32's ``ppeissue.quantity`` fix: any raw
SQL path (perf-baseline ``COPY``, restore-drill dumps, manual ops fixes)
inserting without these columns crashes on ``NOT NULL`` because no DB-side
default exists. Adding ``server_default`` matches the Python ``default=``
already on the model.

Tests are pure AST + closed-loop audit run (no full app boot) so they run
on Win+Py3.13 without the conftest crash.
"""

from __future__ import annotations

import ast
import importlib.util as _ilu
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION_PATH = (
    REPO_ROOT
    / "backend"
    / "app"
    / "migrations"
    / "versions"
    / "20260529_iter37_server_default_cohort_ab.py"
)
AUDIT_PATH = REPO_ROOT / "scripts" / "audit" / "server_default_parity.py"


# Tuple of (table, column, sa_type_name, sa_type_arg_or_none, default_unparsed_source).
# `default_unparsed_source` is what ``ast.unparse`` returns for the
# ``server_default=`` kwarg's AST value node:
#   * ``"'<n>'"`` — int literal stored as str Constant (single-quoted repr)
#   * ``'sa.true()'`` — Call node, unparse returns the source as written
#   * ``"'<val>'"`` — short string literal stored as str Constant
# Using ast.unparse semantics keeps the comparison rigorous and avoids
# re-implementing source reconstruction.
_COHORT_AB: list[tuple[str, str, str, str | int | None, str]] = [
    # --- Subset A: int defaults (7 cols) ---
    ("document_pack_item", "order", "Integer", None, "'0'"),
    ("pack_runs", "selected_rows_count", "Integer", None, "'0'"),
    ("pack_runs", "source_rows_count", "Integer", None, "'0'"),
    ("ppeitem", "default_wear_days", "Integer", None, "'365'"),
    ("ppenorm", "interval_days", "Integer", None, "'365'"),
    ("ppenorm", "quantity", "Integer", None, "'1'"),
    ("warehouseppe", "quantity", "Integer", None, "'0'"),
    # --- Subset A: bool defaults (8 cols) ---
    ("api_key", "is_active", "Boolean", None, "sa.true()"),
    ("document_pack", "is_active", "Boolean", None, "sa.true()"),
    ("document_pack_item", "required", "Boolean", None, "sa.true()"),
    ("package_preset_items", "is_required", "Boolean", None, "sa.true()"),
    ("tenant", "is_active", "Boolean", None, "sa.true()"),
    ("training_plan", "is_mandatory", "Boolean", None, "sa.true()"),
    ("user", "is_active", "Boolean", None, "sa.true()"),
    ("webhook_subscription", "enabled", "Boolean", None, "sa.true()"),
    # --- Subset B: string defaults (4 cols) ---
    ("api_key", "scopes", "String", 255, "'api:read'"),
    ("auditlog", "ip", "String", 64, "'unknown'"),
    ("edo_webhook_inbox", "status", "String", 16, "'received'"),
    ("securityauditlog", "ip", "String", 64, "'unknown'"),
]


def _migration_tree() -> ast.Module:
    return ast.parse(MIGRATION_PATH.read_text(encoding="utf-8"))


def _function(tree: ast.Module, name: str) -> ast.FunctionDef:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    pytest.fail(f"{name}() not found in iter-37 migration")


def _alter_column_calls(fn: ast.FunctionDef) -> list[ast.Call]:
    """Return every ``op.alter_column(...)`` call in fn."""
    out: list[ast.Call] = []
    for node in ast.walk(fn):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "alter_column"
            and len(node.args) >= 2
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[1], ast.Constant)
        ):
            out.append(node)
    return out


def _alter_for(table: str, column: str, fn: ast.FunctionDef) -> ast.Call:
    for call in _alter_column_calls(fn):
        if call.args[0].value == table and call.args[1].value == column:
            return call
    pytest.fail(f"alter_column({table!r}, {column!r}, ...) not found in {fn.name}()")


def _kw_value_source(call: ast.Call, name: str) -> str | None:
    for kw in call.keywords:
        if kw.arg == name:
            return ast.unparse(kw.value)
    return None


# ---------------------------------------------------------------------------
# Migration shape
# ---------------------------------------------------------------------------


def test_migration_revision_chains_to_iter32() -> None:
    tree = _migration_tree()
    revision_assigns = {
        a.target.id: a.value
        for a in tree.body
        if isinstance(a, ast.AnnAssign) and isinstance(a.target, ast.Name)
    }
    rev = revision_assigns.get("revision")
    down = revision_assigns.get("down_revision")
    assert isinstance(rev, ast.Constant) and rev.value == "20260529_iter37_server_default_ab", (
        f"revision = {getattr(rev, 'value', None)!r}"
    )
    assert isinstance(down, ast.Constant) and down.value == "20260528_iter32_business_drift", (
        f"down_revision = {getattr(down, 'value', None)!r}"
    )


def test_cohort_size_pinned_at_nineteen() -> None:
    """Adding a column to this cohort requires also updating _COHORT_AB."""
    tree = _migration_tree()
    upgrade = _function(tree, "upgrade")
    assert len(_alter_column_calls(upgrade)) == len(_COHORT_AB) == 19


def test_no_create_table_in_upgrade() -> None:
    """iter-37 only alters existing columns — no new tables/columns."""
    tree = _migration_tree()
    upgrade = _function(tree, "upgrade")
    for node in ast.walk(upgrade):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in {"create_table", "add_column"}
        ):
            pytest.fail(f"unexpected op.{node.func.attr} call in iter-37 upgrade")


@pytest.mark.parametrize(
    ("table", "column", "_sa_type", "_arg", "_default"), _COHORT_AB
)
def test_cohort_column_has_alter_column_in_upgrade(
    table: str, column: str, _sa_type: str, _arg: str | int | None, _default: str
) -> None:
    tree = _migration_tree()
    upgrade = _function(tree, "upgrade")
    _alter_for(table, column, upgrade)  # raises via pytest.fail if missing


@pytest.mark.parametrize(
    ("table", "column", "sa_type", "_arg", "_default"), _COHORT_AB
)
def test_cohort_column_existing_type_present(
    table: str, column: str, sa_type: str, _arg: str | int | None, _default: str
) -> None:
    tree = _migration_tree()
    upgrade = _function(tree, "upgrade")
    call = _alter_for(table, column, upgrade)
    existing_type_src = _kw_value_source(call, "existing_type")
    assert existing_type_src is not None, (
        f"{table}.{column}: missing existing_type= kwarg"
    )
    assert sa_type in existing_type_src, (
        f"{table}.{column}: existing_type={existing_type_src!r} does not mention {sa_type!r}"
    )


@pytest.mark.parametrize(
    ("table", "column", "_sa_type", "_arg", "_default"), _COHORT_AB
)
def test_cohort_column_existing_nullable_false(
    table: str, column: str, _sa_type: str, _arg: str | int | None, _default: str
) -> None:
    tree = _migration_tree()
    upgrade = _function(tree, "upgrade")
    call = _alter_for(table, column, upgrade)
    src = _kw_value_source(call, "existing_nullable")
    assert src == "False", (
        f"{table}.{column}: existing_nullable={src!r}, expected 'False'"
    )


@pytest.mark.parametrize(
    ("table", "column", "_sa_type", "_arg", "default"), _COHORT_AB
)
def test_cohort_column_server_default_matches_model(
    table: str, column: str, _sa_type: str, _arg: str | int | None, default: str
) -> None:
    tree = _migration_tree()
    upgrade = _function(tree, "upgrade")
    call = _alter_for(table, column, upgrade)
    src = _kw_value_source(call, "server_default")
    assert src == default, (
        f"{table}.{column}: server_default source = {src!r}, expected {default!r}"
    )


def test_downgrade_removes_server_default_for_every_cohort_col() -> None:
    """Every upgrade alter_column has a matching downgrade that resets server_default=None."""
    tree = _migration_tree()
    upgrade = _function(tree, "upgrade")
    downgrade = _function(tree, "downgrade")
    up_pairs = {(c.args[0].value, c.args[1].value) for c in _alter_column_calls(upgrade)}
    down_pairs: set[tuple[str, str]] = set()
    for call in _alter_column_calls(downgrade):
        src = _kw_value_source(call, "server_default")
        if src == "None":
            down_pairs.add((call.args[0].value, call.args[1].value))
    assert up_pairs == down_pairs, (
        f"upgrade-only: {up_pairs - down_pairs}, downgrade-only (with server_default=None): "
        f"{down_pairs - up_pairs}"
    )


# ---------------------------------------------------------------------------
# Closed-loop audit verification (requires audit recognizes alter_column form)
# ---------------------------------------------------------------------------


def _load_audit():
    spec = _ilu.spec_from_file_location("server_default_parity", AUDIT_PATH)
    assert spec is not None and spec.loader is not None
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_audit_no_longer_flags_nineteen_cohort_cols() -> None:
    """After iter-37 + audit alter_column support, the 19 cols disappear from drift."""
    audit = _load_audit()
    drift = audit.run()
    flagged = {(t, c) for (t, c) in drift}
    for table, column, *_ in _COHORT_AB:
        assert (table, column) not in flagged, (
            f"{table}.{column} still flagged by audit — alter_column credit broken or "
            f"migration missing this column"
        )


def test_audit_still_flags_deferred_subset_c_enum_cols() -> None:
    """Sanity: deferred enum cohort (Subset C) is NOT covered by iter-37 and remains flagged."""
    audit = _load_audit()
    drift = audit.run()
    flagged = {(t, c) for (t, c) in drift}
    # Sample a few deferred enum cols to ensure we didn't accidentally drop the
    # whole audit signal (e.g. by breaking the model-scan).
    expected_still_flagged = {
        ("incident", "severity"),
        ("incident", "status"),
        ("permit", "status"),
        ("tenant", "kind"),  # deferred: PG-enum column type
    }
    missing = expected_still_flagged - flagged
    assert not missing, (
        f"audit accidentally dropped {missing} from drift — model-scan regression"
    )
