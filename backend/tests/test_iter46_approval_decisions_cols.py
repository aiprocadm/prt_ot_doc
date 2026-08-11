"""Pin tests for iter-46 approval_decisions model-col closure migration.

Closes the ``approval_decisions`` business-drift table surfaced by
``column_drift_lite`` (Session 94 candidate #2). Five columns were added to
the ``ApprovalDecision`` model over the orchestration build-out
(``backend/app/models/approval_workflow.py:170-178``) but the only migration
that touches the table — ``20250425_edo_approval_signature_mvp.py:130`` —
predates them and creates just ``request_id, step_index, actor_user_id,
decision, comment`` + base cols. The five drift cols are:

    approval_instance_id        FK -> approval_instances.id      (nullable, indexed)
    approval_instance_step_id   FK -> approval_instance_steps.id (nullable, indexed)
    payload_json                JSON                             (nullable)
    ip                          String(64)                       (nullable)
    user_agent                  String(512)                      (nullable)

They are live read/written: ``app/modules/approvals/service.py:140-148``
constructs ``ApprovalDecision(approval_instance_id=..., approval_instance_step_id=...)``
and ``app/api/routes/approval_orchestration.py:293`` filters on
``approval_instance_id``. So this is real drift (option a), not a rename or
intentional design.

Ordering nuance (vs iter-40): the FK-target tables ``approval_instances`` /
``approval_instance_steps`` are created by ``20260330_next57`` and the table
itself by ``20250425_edo_approval_signature_mvp`` — both on a DIFFERENT branch
than ``iter38`` (this migration's ``down_revision``). Under ``alembic upgrade
heads`` cross-branch ordering is only guaranteed by ``depends_on``, so iter-46
declares an explicit dependency on both (iter-40 needed none — its FK targets
sat in iter38's lineage).

Tests are pure AST + audit-integration (no full app boot) so they run on
Win+Py3.13 without the conftest crash. Mirrors iter-40 pattern (PR #604).
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
    / "20260529_iter46_approval_decisions_cols.py"
)

_REVISION = "20260529_iter46_approval_decisions_cols"
_DOWN_REVISION = "20260529_iter38_server_default_c"
# mvp creates the approval_decisions table; next57 creates the FK-target tables.
_EXPECTED_DEPENDS_ON = {
    "20250425_edo_approval_signature_mvp",
    "20260330_next57",
}

_TABLE = "approval_decisions"

# Tuple of (column, nullable, fk_target_table, ondelete_action).
#   fk_target_table is None  -> plain column (no FK)
#   fk_target_table set, ondelete None -> FK with NO ondelete clause (model has none)
_COHORT: list[tuple[str, bool, str | None, str | None]] = [
    ("approval_instance_id", True, "approval_instances", None),
    ("approval_instance_step_id", True, "approval_instance_steps", None),
    ("payload_json", True, None, None),
    ("ip", True, None, None),
    ("user_agent", True, None, None),
]

_EXPECTED_INDEXES: list[tuple[str, str, list[str]]] = [
    (
        "ix_approval_decisions_approval_instance_id",
        "approval_decisions",
        ["approval_instance_id"],
    ),
    (
        "ix_approval_decisions_approval_instance_step_id",
        "approval_decisions",
        ["approval_instance_step_id"],
    ),
]


def _migration_tree() -> ast.Module:
    return ast.parse(MIGRATION_PATH.read_text(encoding="utf-8"))


def _upgrade_fn(tree: ast.Module) -> ast.FunctionDef:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "upgrade":
            return node
    pytest.fail("upgrade() not found in iter-46 migration")


def _downgrade_fn(tree: ast.Module) -> ast.FunctionDef:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "downgrade":
            return node
    pytest.fail("downgrade() not found in iter-46 migration")


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


def _strings_in(node: ast.expr | None) -> set[str]:
    """Collect string constants from a Constant / Tuple / List AST node."""
    if node is None:
        return set()
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return {node.value}
    if isinstance(node, (ast.Tuple, ast.List)):
        out: set[str] = set()
        for elt in node.elts:
            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                out.add(elt.value)
        return out
    return set()


def _module_assigns(tree: ast.Module) -> dict[str, ast.expr]:
    out: dict[str, ast.expr] = {}
    for a in tree.body:
        if isinstance(a, ast.AnnAssign) and isinstance(a.target, ast.Name) and a.value is not None:
            out[a.target.id] = a.value
    return out


def test_migration_revision_chains_to_iter38() -> None:
    assigns = _module_assigns(_migration_tree())
    rev = assigns.get("revision")
    down = assigns.get("down_revision")
    assert isinstance(rev, ast.Constant) and rev.value == _REVISION
    assert isinstance(down, ast.Constant) and down.value == _DOWN_REVISION


def test_migration_depends_on_table_and_fk_targets() -> None:
    """iter-46's add_column targets live on a different branch than iter38.

    Under ``alembic upgrade heads`` the only thing that orders this migration
    after the table-creating (mvp) and FK-target-creating (next57) migrations
    is ``depends_on``. Pin it so a future edit can't silently drop the edge
    and reintroduce a runtime ``relation does not exist`` failure.
    """
    assigns = _module_assigns(_migration_tree())
    deps = _strings_in(assigns.get("depends_on"))
    assert _EXPECTED_DEPENDS_ON <= deps, (
        f"depends_on must include {_EXPECTED_DEPENDS_ON}, AST shows {deps}"
    )


@pytest.mark.parametrize(("column", "_nullable", "_fk_target", "_ondelete"), _COHORT)
def test_cohort_column_present_in_upgrade(
    column: str, _nullable: bool, _fk_target: str | None, _ondelete: str | None,
) -> None:
    upgrade = _upgrade_fn(_migration_tree())
    _column_call_for(column, upgrade)  # raises pytest.fail if missing


@pytest.mark.parametrize(("column", "nullable", "_fk_target", "_ondelete"), _COHORT)
def test_cohort_column_nullable_matches_spec(
    column: str, nullable: bool, _fk_target: str | None, _ondelete: str | None,
) -> None:
    upgrade = _upgrade_fn(_migration_tree())
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
    upgrade = _upgrade_fn(_migration_tree())
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


@pytest.mark.parametrize(("column", "_n", "fk_target", "ondelete"), _COHORT)
def test_cohort_column_ondelete_matches_spec(
    column: str, _n: bool, fk_target: str | None, ondelete: str | None,
) -> None:
    """The ``ApprovalDecision`` FK cols declare NO ondelete (plain FK), unlike
    iter-40's CASCADE/SET NULL cohort. For FK cols expect ondelete absent;
    for non-FK cols the check is N/A."""
    if fk_target is None:
        return  # not a FK; ondelete check N/A
    upgrade = _upgrade_fn(_migration_tree())
    col_call = _column_call_for(column, upgrade)
    fk_args = [
        arg for arg in col_call.args
        if isinstance(arg, ast.Call)
        and isinstance(arg.func, ast.Attribute)
        and arg.func.attr == "ForeignKey"
    ]
    assert fk_args, f"{_TABLE}.{column}: expected FK"
    ondelete_kw = None
    for kw in fk_args[0].keywords:
        if kw.arg == "ondelete" and isinstance(kw.value, ast.Constant):
            ondelete_kw = kw.value.value
    assert ondelete_kw == ondelete, (
        f"{_TABLE}.{column}: expected ondelete={ondelete!r}, AST shows {ondelete_kw!r}"
    )


def test_indexes_for_fk_columns_present_in_upgrade() -> None:
    """Both FK cols get a non-unique index — matches the model's
    ``mapped_column(ForeignKey(...), ..., index=True)`` declarations."""
    upgrade = _upgrade_fn(_migration_tree())
    found: set[tuple[str, str, tuple[str, ...]]] = set()
    for node in ast.walk(upgrade):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "create_index"
            and len(node.args) >= 3
        ):
            continue
        idx_name, table, cols = node.args[0], node.args[1], node.args[2]
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
    assert expected <= found, f"missing create_index calls: {expected - found}"


def test_upgrade_and_downgrade_symmetric() -> None:
    """Each upgrade add_column has a matching downgrade drop_column, and each
    upgrade create_index has a matching drop_index."""
    tree = _migration_tree()
    upgrade = _upgrade_fn(tree)
    downgrade = _downgrade_fn(tree)
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
    upgrade_idx = {
        node.args[0].value
        for node in ast.walk(upgrade)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "create_index"
        and node.args
        and isinstance(node.args[0], ast.Constant)
    }
    downgrade_idx = {
        node.args[0].value
        for node in ast.walk(downgrade)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "drop_index"
        and node.args
        and isinstance(node.args[0], ast.Constant)
    }
    assert upgrade_idx == downgrade_idx, (
        f"index symmetry broken: upgrade-only={upgrade_idx - downgrade_idx}, "
        f"downgrade-only={downgrade_idx - upgrade_idx}"
    )


def test_cohort_size_pinned_at_five() -> None:
    """Adding/removing a col from this cohort requires updating _COHORT too."""
    upgrade = _upgrade_fn(_migration_tree())
    assert len(_add_column_calls(upgrade)) == len(_COHORT)


def test_no_create_table_in_upgrade() -> None:
    """iter-46 only adds columns to existing approval_decisions — no new tables."""
    upgrade = _upgrade_fn(_migration_tree())
    for node in ast.walk(upgrade):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "create_table"
        ):
            pytest.fail("unexpected op.create_table call in iter-46 upgrade")


def _load_audit():
    audit_path = REPO_ROOT / "scripts" / "audit" / "column_drift_lite.py"
    spec = importlib.util.spec_from_file_location("column_drift_lite", audit_path)
    assert spec is not None and spec.loader is not None
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)
    return audit


def test_audit_credits_iter46_columns() -> None:
    """Closed-loop: after iter-46 ships, ``column_drift_lite`` credits the 5
    cols to approval_decisions."""
    audit = _load_audit()
    credited = audit.collect_migration_columns().get(_TABLE, set())
    for column, *_ in _COHORT:
        assert column in credited, (
            f"audit doesn't credit {_TABLE}.{column} after iter-46 — "
            f"closed-loop broken (credited={sorted(credited)})"
        )


def test_audit_drift_approval_decisions_cleared_after_iter46() -> None:
    """Closed-loop: approval_decisions must no longer appear in the drift list."""
    audit = _load_audit()
    models = audit.find_versioned_models()
    migration_cols = audit.collect_migration_columns()
    drift = audit.compute_drift(models, migration_cols)
    drift_tables = {info.tablename for info, _missing in drift}
    assert _TABLE not in drift_tables, (
        "approval_decisions should be cleared by iter-46"
    )
