"""Pin tests for iter-40 training_certificates legacy-cols migration.

Closes one of the 5 column_drift_lite business-drift tables. The 4 cols
(`course_id`, `session_id`, `plan_id`, `number`) plus a
`UniqueConstraint(tenant_id, number)` were added to the
``TrainingCertificate`` model in commit ``58b428e`` ("Fix training
certificate model mapping for next APIs", 2026-03-09) but the
``training_certificates`` migration (``20260317_next46_training_briefings_offline.py:113``)
predates that commit and doesn't carry them.

Tests are pure AST + audit-integration (no full app boot) so they run on
Win+Py3.13 without the conftest crash. Mirrors iter-32 pattern (PR #604).
"""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION_PATH = (
    REPO_ROOT
    / "backend"
    / "app"
    / "migrations"
    / "versions"
    / "20260529_iter40_training_certificates_legacy_cols.py"
)


# Tuple of (column, nullable, fk_target_table, ondelete_action).
# None for fk_target_table means no FK (plain String column).
_COHORT: list[tuple[str, bool, str | None, str | None]] = [
    ("course_id", True, "training_course", "CASCADE"),
    ("session_id", True, "training_session", "SET NULL"),
    ("plan_id", True, "training_plan", "SET NULL"),
    ("number", True, None, None),
]

_EXPECTED_INDEXES: list[tuple[str, str, list[str]]] = [
    ("ix_training_certificates_course_id", "training_certificates", ["course_id"]),
    ("ix_training_certificates_session_id", "training_certificates", ["session_id"]),
    ("ix_training_certificates_plan_id", "training_certificates", ["plan_id"]),
]

_TABLE = "training_certificates"


def _migration_tree() -> ast.Module:
    return ast.parse(MIGRATION_PATH.read_text(encoding="utf-8"))


def _upgrade_fn(tree: ast.Module) -> ast.FunctionDef:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "upgrade":
            return node
    pytest.fail("upgrade() not found in iter-40 migration")


def _downgrade_fn(tree: ast.Module) -> ast.FunctionDef:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "downgrade":
            return node
    pytest.fail("downgrade() not found in iter-40 migration")


def _add_column_calls(fn: ast.FunctionDef) -> list[tuple[str, ast.Call]]:
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


def _column_call_for(column: str, fn: ast.FunctionDef) -> ast.Call:
    for tn, call in _add_column_calls(fn):
        if tn != _TABLE:
            continue
        col_arg = call.args[1]
        if (
            isinstance(col_arg, ast.Call)
            and col_arg.args
            and isinstance(col_arg.args[0], ast.Constant)
            and col_arg.args[0].value == column
        ):
            return col_arg
    pytest.fail(f"add_column({_TABLE!r}, sa.Column({column!r}, ...)) not in upgrade()")


def test_migration_revision_chains_to_iter38() -> None:
    tree = _migration_tree()
    revision_assigns = {
        a.target.id: a.value
        for a in tree.body
        if isinstance(a, ast.AnnAssign) and isinstance(a.target, ast.Name)
    }
    rev = revision_assigns.get("revision")
    down = revision_assigns.get("down_revision")
    assert isinstance(rev, ast.Constant) and rev.value == "20260529_iter40_tc_legacy_cols"
    assert isinstance(down, ast.Constant) and down.value == "20260529_iter38_server_default_c"


@pytest.mark.parametrize(("column", "_nullable", "_fk_target", "_ondelete"), _COHORT)
def test_cohort_column_present_in_upgrade(
    column: str, _nullable: bool, _fk_target: str | None, _ondelete: str | None,
) -> None:
    tree = _migration_tree()
    upgrade = _upgrade_fn(tree)
    _column_call_for(column, upgrade)  # raises pytest.fail if missing


@pytest.mark.parametrize(("column", "nullable", "_fk_target", "_ondelete"), _COHORT)
def test_cohort_column_nullable_matches_spec(
    column: str, nullable: bool, _fk_target: str | None, _ondelete: str | None,
) -> None:
    tree = _migration_tree()
    upgrade = _upgrade_fn(tree)
    col_call = _column_call_for(column, upgrade)
    nullable_kw = None
    for kw in col_call.keywords:
        if kw.arg == "nullable" and isinstance(kw.value, ast.Constant):
            nullable_kw = kw.value.value
    assert nullable_kw is nullable, (
        f"{_TABLE}.{column}: expected nullable={nullable}, AST shows {nullable_kw!r}"
    )


@pytest.mark.parametrize(("column", "_n", "fk_target", "_ondelete"), _COHORT)
def test_cohort_column_fk_target_present_when_expected(
    column: str, _n: bool, fk_target: str | None, _ondelete: str | None,
) -> None:
    tree = _migration_tree()
    upgrade = _upgrade_fn(tree)
    col_call = _column_call_for(column, upgrade)
    fk_args = [
        arg for arg in col_call.args
        if isinstance(arg, ast.Call)
        and isinstance(arg.func, ast.Attribute)
        and arg.func.attr == "ForeignKey"
    ]
    if fk_target is None:
        assert not fk_args, f"{_TABLE}.{column}: unexpected ForeignKey() declared"
    else:
        assert fk_args, f"{_TABLE}.{column}: expected ForeignKey({fk_target}.id), AST has none"
        first = fk_args[0].args[0]
        assert isinstance(first, ast.Constant) and isinstance(first.value, str)
        assert first.value == f"{fk_target}.id", (
            f"{_TABLE}.{column}: FK target expected {fk_target}.id, got {first.value!r}"
        )


@pytest.mark.parametrize(("column", "_n", "_fk", "ondelete"), _COHORT)
def test_cohort_column_ondelete_matches_spec(
    column: str, _n: bool, _fk: str | None, ondelete: str | None,
) -> None:
    """For FK cols, verify ondelete behavior matches the model declaration.

    Model has:
      course_id:  ondelete=CASCADE  (delete cascade — legacy course mandatory)
      session_id: ondelete=SET NULL (optional retro link)
      plan_id:    ondelete=SET NULL (optional retro link)
    """
    tree = _migration_tree()
    upgrade = _upgrade_fn(tree)
    col_call = _column_call_for(column, upgrade)
    fk_args = [
        arg for arg in col_call.args
        if isinstance(arg, ast.Call)
        and isinstance(arg.func, ast.Attribute)
        and arg.func.attr == "ForeignKey"
    ]
    if ondelete is None:
        return  # not a FK; ondelete check N/A
    assert fk_args, f"{_TABLE}.{column}: expected FK with ondelete={ondelete}"
    ondelete_kw = None
    for kw in fk_args[0].keywords:
        if kw.arg == "ondelete" and isinstance(kw.value, ast.Constant):
            ondelete_kw = kw.value.value
    assert ondelete_kw == ondelete, (
        f"{_TABLE}.{column}: expected ondelete={ondelete}, AST shows {ondelete_kw!r}"
    )


def test_indexes_for_fk_columns_present_in_upgrade() -> None:
    """The 3 FK cols each get a non-unique index — matches model's
    ``mapped_column(ForeignKey(...), ..., index=True)`` declarations."""
    tree = _migration_tree()
    upgrade = _upgrade_fn(tree)
    found: set[tuple[str, str, tuple[str, ...]]] = set()
    for node in ast.walk(upgrade):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "create_index"
            and len(node.args) >= 3
        ):
            continue
        idx_name = node.args[0]
        table = node.args[1]
        cols = node.args[2]
        if not (
            isinstance(idx_name, ast.Constant) and isinstance(idx_name.value, str)
            and isinstance(table, ast.Constant) and isinstance(table.value, str)
            and isinstance(cols, ast.List)
        ):
            continue
        col_names = tuple(
            elt.value for elt in cols.elts
            if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
        )
        found.add((idx_name.value, table.value, col_names))
    expected = {(name, table, tuple(cols)) for name, table, cols in _EXPECTED_INDEXES}
    assert expected <= found, (
        f"missing create_index calls: {expected - found}"
    )


def test_unique_constraint_present_in_upgrade() -> None:
    """``UniqueConstraint(tenant_id, number)`` must be added to match
    ``__table_args__`` in the model."""
    tree = _migration_tree()
    upgrade = _upgrade_fn(tree)
    for node in ast.walk(upgrade):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "create_unique_constraint"
            and len(node.args) >= 3
        ):
            continue
        name = node.args[0]
        table = node.args[1]
        cols = node.args[2]
        if (
            isinstance(name, ast.Constant) and name.value == "uq_training_certificate_number"
            and isinstance(table, ast.Constant) and table.value == _TABLE
            and isinstance(cols, ast.List)
        ):
            col_names = [
                elt.value for elt in cols.elts
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
            ]
            assert col_names == ["tenant_id", "number"], (
                f"uq_training_certificate_number cols: expected [tenant_id, number], got {col_names}"
            )
            return
    pytest.fail("create_unique_constraint('uq_training_certificate_number', ...) missing")


def test_upgrade_and_downgrade_symmetric() -> None:
    """Each upgrade add_column has a matching downgrade drop_column,
    each upgrade create_index has a matching drop_index, and the
    UniqueConstraint is dropped via drop_constraint."""
    tree = _migration_tree()
    upgrade = _upgrade_fn(tree)
    downgrade = _downgrade_fn(tree)
    # Columns
    upgrade_cols = {
        (tn, call.args[1].args[0].value)
        for tn, call in _add_column_calls(upgrade)
        if isinstance(call.args[1], ast.Call)
        and call.args[1].args
        and isinstance(call.args[1].args[0], ast.Constant)
    }
    downgrade_cols: set[tuple[str, str]] = set()
    for node in ast.walk(downgrade):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "drop_column"
            and len(node.args) >= 2
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[1], ast.Constant)
        ):
            downgrade_cols.add((node.args[0].value, node.args[1].value))
    assert upgrade_cols == downgrade_cols, (
        f"col symmetry broken: upgrade-only={upgrade_cols - downgrade_cols}, "
        f"downgrade-only={downgrade_cols - upgrade_cols}"
    )
    # Indexes
    upgrade_idx = set()
    for node in ast.walk(upgrade):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "create_index"
            and node.args
            and isinstance(node.args[0], ast.Constant)
        ):
            upgrade_idx.add(node.args[0].value)
    downgrade_idx = set()
    for node in ast.walk(downgrade):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "drop_index"
            and node.args
            and isinstance(node.args[0], ast.Constant)
        ):
            downgrade_idx.add(node.args[0].value)
    assert upgrade_idx == downgrade_idx, (
        f"index symmetry broken: upgrade-only={upgrade_idx - downgrade_idx}, "
        f"downgrade-only={downgrade_idx - upgrade_idx}"
    )
    # UniqueConstraint
    has_drop_constraint = any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "drop_constraint"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and node.args[0].value == "uq_training_certificate_number"
        for node in ast.walk(downgrade)
    )
    assert has_drop_constraint, "downgrade missing drop_constraint('uq_training_certificate_number', ...)"


def test_cohort_size_pinned_at_four() -> None:
    """Adding/removing a col from this cohort requires updating _COHORT too."""
    tree = _migration_tree()
    upgrade = _upgrade_fn(tree)
    assert len(_add_column_calls(upgrade)) == len(_COHORT)


def test_no_create_table_in_upgrade() -> None:
    """iter-40 only adds columns to existing training_certificates — no new tables."""
    tree = _migration_tree()
    upgrade = _upgrade_fn(tree)
    for node in ast.walk(upgrade):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "create_table"
        ):
            pytest.fail("unexpected op.create_table call in iter-40 upgrade")


def test_audit_credits_iter40_columns() -> None:
    """Closed-loop: after iter-40 ships, ``column_drift_lite`` credits the
    4 cols to training_certificates and drops it from the business-drift list.
    """
    audit_path = REPO_ROOT / "scripts" / "audit" / "column_drift_lite.py"
    spec = importlib.util.spec_from_file_location("column_drift_lite", audit_path)
    assert spec is not None and spec.loader is not None
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)

    migration_cols = audit.collect_migration_columns()
    credited = migration_cols.get(_TABLE, set())
    for column, *_ in _COHORT:
        assert column in credited, (
            f"audit doesn't credit {_TABLE}.{column} after iter-40 — "
            f"closed-loop broken (credited={sorted(credited)})"
        )


def test_audit_drift_training_certificates_cleared_after_iter40() -> None:
    """Closed-loop scoped to iter-40's contribution: training_certificates
    must be cleared by the legacy-col cohort closure.

    Originally also asserted that the 4 design-blocked tables (incident,
    incident_log, incident_person, journalentry) remained flagged. That
    sibling assertion was correct in isolation but breaks once
    iter-41 / iter-42 land (those close journalentry + incident family).
    Relaxed to a single-table check; integration-level "all drift cleared"
    assertion is owned by iter-42's closed-loop test.
    """
    audit_path = REPO_ROOT / "scripts" / "audit" / "column_drift_lite.py"
    spec = importlib.util.spec_from_file_location("column_drift_lite", audit_path)
    assert spec is not None and spec.loader is not None
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)

    models = audit.find_versioned_models()
    migration_cols = audit.collect_migration_columns()
    drift = audit.compute_drift(models, migration_cols)
    drift_tables = {info.tablename for info, _missing in drift}
    assert _TABLE not in drift_tables, (
        "training_certificates should be cleared by iter-40"
    )
