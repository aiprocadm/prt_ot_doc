"""Pin tests for iter-32 business-drift cohort migration.

Closes the safe-to-ship subset of drift discovered by
``scripts/audit/column_drift_lite.py`` (Session 80): nullable columns and
columns with safe server-side defaults. NOT NULL FK columns + naming-
drift cases are deferred to follow-up iterations that require backfill /
design decisions.

Tests are pure AST + ORM inspection (no full app boot) so they run on
Win+Py3.13 without the conftest crash.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION_PATH = (
    REPO_ROOT
    / "backend"
    / "app"
    / "migrations"
    / "versions"
    / "20260528_iter32_business_drift_cohort.py"
)


# Tuple of (table, column, nullable, has_fk_target, has_server_default).
_COHORT = [
    ("permit", "position_id", True, True, False),
    ("ppeissue", "item_id", True, True, False),
    ("ppeissue", "quantity", False, False, True),
    ("ppeissue", "wear_days", True, False, False),
    ("riskmap", "document_pack_id", True, True, False),
    ("riskmap", "position_id", True, True, False),
    ("riskmap", "site_id", True, True, False),
]


def _migration_tree() -> ast.Module:
    return ast.parse(MIGRATION_PATH.read_text(encoding="utf-8"))


def _upgrade_fn(tree: ast.Module) -> ast.FunctionDef:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "upgrade":
            return node
    pytest.fail("upgrade() not found in iter-32 migration")


def _downgrade_fn(tree: ast.Module) -> ast.FunctionDef:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "downgrade":
            return node
    pytest.fail("downgrade() not found in iter-32 migration")


def _add_column_calls(fn: ast.FunctionDef) -> list[tuple[str, ast.Call]]:
    """Return [(tablename, full_add_column_call_node)] for each add_column."""
    calls: list[tuple[str, ast.Call]] = []
    for node in ast.walk(fn):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "add_column"
            and len(node.args) >= 2
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            calls.append((node.args[0].value, node))
    return calls


def _column_call_for(table: str, column: str, fn: ast.FunctionDef) -> ast.Call:
    """Return the ``sa.Column("col", ...)`` AST call for a given add_column."""
    for tn, call in _add_column_calls(fn):
        if tn != table:
            continue
        col_arg = call.args[1]
        if (
            isinstance(col_arg, ast.Call)
            and col_arg.args
            and isinstance(col_arg.args[0], ast.Constant)
            and col_arg.args[0].value == column
        ):
            return col_arg
    pytest.fail(f"add_column({table!r}, sa.Column({column!r}, ...)) not in upgrade()")


def test_migration_revision_chains_to_iter29() -> None:
    tree = _migration_tree()
    revision_assigns = {
        a.target.id: a.value
        for a in tree.body
        if isinstance(a, ast.AnnAssign) and isinstance(a.target, ast.Name)
    }
    rev = revision_assigns.get("revision")
    down = revision_assigns.get("down_revision")
    assert isinstance(rev, ast.Constant) and rev.value == "20260528_iter32_business_drift"
    assert isinstance(down, ast.Constant) and down.value == "20260528_iter29_version_retrofit"


@pytest.mark.parametrize(("table", "column", "_nullable", "_has_fk", "_has_default"), _COHORT)
def test_cohort_column_present_in_upgrade(
    table: str, column: str, _nullable: bool, _has_fk: bool, _has_default: bool
) -> None:
    tree = _migration_tree()
    upgrade = _upgrade_fn(tree)
    # Will raise via pytest.fail if missing.
    _column_call_for(table, column, upgrade)


@pytest.mark.parametrize(("table", "column", "nullable", "_has_fk", "_has_default"), _COHORT)
def test_cohort_column_nullable_matches_spec(
    table: str, column: str, nullable: bool, _has_fk: bool, _has_default: bool
) -> None:
    tree = _migration_tree()
    upgrade = _upgrade_fn(tree)
    col_call = _column_call_for(table, column, upgrade)
    nullable_kw = None
    for kw in col_call.keywords:
        if kw.arg == "nullable" and isinstance(kw.value, ast.Constant):
            nullable_kw = kw.value.value
    assert nullable_kw is nullable, (
        f"{table}.{column}: expected nullable={nullable}, AST shows {nullable_kw!r}"
    )


@pytest.mark.parametrize(("table", "column", "_n", "has_fk", "_hd"), _COHORT)
def test_cohort_column_fk_target_present_when_expected(
    table: str, column: str, _n: bool, has_fk: bool, _hd: bool
) -> None:
    tree = _migration_tree()
    upgrade = _upgrade_fn(tree)
    col_call = _column_call_for(table, column, upgrade)
    fk_args = [
        arg for arg in col_call.args
        if isinstance(arg, ast.Call)
        and isinstance(arg.func, ast.Attribute)
        and arg.func.attr == "ForeignKey"
    ]
    if has_fk:
        assert fk_args, f"{table}.{column}: expected ForeignKey(), AST has none"
        # Sanity: FK first arg is a string like "<table>.id"
        first = fk_args[0].args[0]
        assert isinstance(first, ast.Constant) and isinstance(first.value, str)
        assert first.value.endswith(".id"), (
            f"{table}.{column}: FK target {first.value!r} doesn't end with .id"
        )
    else:
        assert not fk_args, f"{table}.{column}: unexpected ForeignKey() declared"


@pytest.mark.parametrize(("table", "column", "_n", "_hf", "has_default"), _COHORT)
def test_cohort_column_server_default_when_expected(
    table: str, column: str, _n: bool, _hf: bool, has_default: bool
) -> None:
    tree = _migration_tree()
    upgrade = _upgrade_fn(tree)
    col_call = _column_call_for(table, column, upgrade)
    has_kw = any(kw.arg == "server_default" for kw in col_call.keywords)
    assert has_kw is has_default, (
        f"{table}.{column}: expected server_default present={has_default}, got {has_kw}"
    )


def test_upgrade_and_downgrade_symmetric() -> None:
    """Each upgrade add_column has a matching downgrade drop_column."""
    tree = _migration_tree()
    upgrade = _upgrade_fn(tree)
    downgrade = _downgrade_fn(tree)
    upgrade_pairs = {
        (tn, call.args[1].args[0].value)
        for tn, call in _add_column_calls(upgrade)
        if isinstance(call.args[1], ast.Call)
        and call.args[1].args
        and isinstance(call.args[1].args[0], ast.Constant)
    }
    downgrade_pairs: set[tuple[str, str]] = set()
    for node in ast.walk(downgrade):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "drop_column"
            and len(node.args) >= 2
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[1], ast.Constant)
        ):
            downgrade_pairs.add((node.args[0].value, node.args[1].value))
    assert upgrade_pairs == downgrade_pairs, (
        f"upgrade-only: {upgrade_pairs - downgrade_pairs}, "
        f"downgrade-only: {downgrade_pairs - upgrade_pairs}"
    )


def test_cohort_size_pinned_at_seven() -> None:
    """Adding a new table/column to this cohort requires updating _COHORT too."""
    tree = _migration_tree()
    upgrade = _upgrade_fn(tree)
    assert len(_add_column_calls(upgrade)) == len(_COHORT)


def test_no_create_table_in_upgrade() -> None:
    """iter-32 only adds columns to existing tables — no new tables."""
    tree = _migration_tree()
    upgrade = _upgrade_fn(tree)
    for node in ast.walk(upgrade):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "create_table"
        ):
            pytest.fail("unexpected op.create_table call in iter-32 upgrade")


def test_audit_credits_iter32_columns() -> None:
    """Integration: after iter-32 ships, column_drift_lite should NOT report the 7 cols.

    Closed-loop verification — same shape of pin test that iter-29 + audit v3
    enabled. Skipped when ``column_drift_lite.py`` is absent (it lives on the
    pending PR #603 branch ``feat/audit-column-drift-lite``); once both land
    on main this test asserts the closed loop.
    """
    audit_path = REPO_ROOT / "scripts" / "audit" / "column_drift_lite.py"
    if not audit_path.exists():
        pytest.skip("column_drift_lite.py absent — pending PR #603")
    import importlib.util as _ilu
    spec = _ilu.spec_from_file_location("column_drift_lite", audit_path)
    assert spec is not None and spec.loader is not None
    audit = _ilu.module_from_spec(spec)
    spec.loader.exec_module(audit)

    migration_cols = audit.collect_migration_columns()
    for table, column, *_ in _COHORT:
        assert column in migration_cols.get(table, set()), (
            f"audit doesn't credit {table}.{column} after iter-32 — closed-loop verify broken"
        )
