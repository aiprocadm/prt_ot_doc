"""Pin tests for iter-34 ppenorm.hazard_id NOT NULL FK backfill migration.

Closes the first of the two NOT-NULL-FK items iter-32 deliberately deferred:

    ppenorm:   hazard_id    (NOT NULL FK — no safe server_default)
    riskmap:   company_id   (NOT NULL FK — no safe server_default)

Bug class: ORM-Migration drift, flavor (b) — column declared on the model
(``models.py::PPENorm.hazard_id``) but absent from the creator migration
(``6b6dee7c951f_initial_schema.py`` line 620 ``op.create_table('ppenorm', ...)``
lists position_id/item_name/quantity/interval_days/tenant_id but no hazard_id).

Strategy: 3 in-migration steps because hazard_id has no safe server_default.

    Step 1: ADD COLUMN hazard_id (nullable=True) + FK + index.
    Step 2: ``DELETE FROM ppenorm WHERE hazard_id IS NULL`` — table was
            effectively read-only since deploy (every ORM INSERT broke on
            Postgres ``UndefinedColumnError`` per iter-32 docstring;
            SQLite-tolerant stale rows lack a meaningful hazard_id and
            would violate the model's NOT NULL invariant anyway).
    Step 3: ``ALTER COLUMN hazard_id SET NOT NULL`` (batch_alter for SQLite).

Plus matching ``UniqueConstraint(tenant_id, position_id, hazard_id,
item_name)`` per model ``__table_args__`` — hazard_id only makes sense
together with its unique tuple companion.

Tests are pure AST + module-spec inspection (no full app boot) so they run
on Win+Py3.13 without the conftest crash (see ``[[local-env-drift-windows]]``).
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
    / "20260529_iter34_ppenorm_hazard_id_backfill.py"
)


def _migration_tree() -> ast.Module:
    if not MIGRATION_PATH.exists():
        pytest.fail(f"iter-34 migration not found at {MIGRATION_PATH}")
    return ast.parse(MIGRATION_PATH.read_text(encoding="utf-8"))


def _upgrade_fn(tree: ast.Module) -> ast.FunctionDef:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "upgrade":
            return node
    pytest.fail("upgrade() not found in iter-34 migration")


def _downgrade_fn(tree: ast.Module) -> ast.FunctionDef:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "downgrade":
            return node
    pytest.fail("downgrade() not found in iter-34 migration")


def _calls_named(fn: ast.FunctionDef, attr: str) -> list[ast.Call]:
    """All op.<attr>(...) calls (or batch_op.<attr>(...)) in fn."""
    found: list[ast.Call] = []
    for node in ast.walk(fn):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == attr
        ):
            found.append(node)
    return found


def _add_column_for(table: str, column: str, fn: ast.FunctionDef) -> ast.Call:
    """Return the inner ``sa.Column("column", ...)`` AST call for an add_column."""
    for call in _calls_named(fn, "add_column"):
        if (
            len(call.args) >= 2
            and isinstance(call.args[0], ast.Constant)
            and call.args[0].value == table
            and isinstance(call.args[1], ast.Call)
            and call.args[1].args
            and isinstance(call.args[1].args[0], ast.Constant)
            and call.args[1].args[0].value == column
        ):
            return call.args[1]
    pytest.fail(f"add_column({table!r}, sa.Column({column!r}, ...)) not in upgrade()")


def _keyword_value(call: ast.Call, name: str) -> object | None:
    for kw in call.keywords:
        if kw.arg == name and isinstance(kw.value, ast.Constant):
            return kw.value.value
    return None


def test_migration_revision_chains_to_iter32() -> None:
    tree = _migration_tree()
    revision_assigns = {
        a.target.id: a.value
        for a in tree.body
        if isinstance(a, ast.AnnAssign) and isinstance(a.target, ast.Name)
    }
    rev = revision_assigns.get("revision")
    down = revision_assigns.get("down_revision")
    assert isinstance(rev, ast.Constant) and rev.value == "20260529_iter34_ppenorm_hazard"
    assert isinstance(down, ast.Constant) and down.value == "20260528_iter32_business_drift"


def test_hazard_id_column_added_to_ppenorm() -> None:
    tree = _migration_tree()
    upgrade = _upgrade_fn(tree)
    _add_column_for("ppenorm", "hazard_id", upgrade)  # raises via pytest.fail if missing


def test_hazard_id_initially_added_nullable_for_safe_backfill() -> None:
    """Step 1 of the 3-step pattern: add column nullable=True so existing
    rows (if any) survive ADD COLUMN; Step 3 alters to NOT NULL once
    orphans are gone.
    """
    tree = _migration_tree()
    upgrade = _upgrade_fn(tree)
    col_call = _add_column_for("ppenorm", "hazard_id", upgrade)
    assert _keyword_value(col_call, "nullable") is True, (
        "hazard_id must be added with nullable=True so Step 2 DELETE can run "
        "before Step 3 ALTER NOT NULL — otherwise Postgres rejects ADD COLUMN"
    )


def test_hazard_id_fk_targets_risk_hazards_with_cascade() -> None:
    """Model: ``ForeignKey('risk_hazards.id', ondelete='CASCADE')``."""
    tree = _migration_tree()
    upgrade = _upgrade_fn(tree)
    col_call = _add_column_for("ppenorm", "hazard_id", upgrade)
    fk_calls = [
        arg for arg in col_call.args
        if isinstance(arg, ast.Call)
        and isinstance(arg.func, ast.Attribute)
        and arg.func.attr == "ForeignKey"
    ]
    assert fk_calls, "hazard_id must declare sa.ForeignKey(...) inline"
    fk = fk_calls[0]
    target = fk.args[0] if fk.args else None
    assert isinstance(target, ast.Constant) and target.value == "risk_hazards.id"
    ondelete = _keyword_value(fk, "ondelete")
    assert ondelete == "CASCADE", (
        f"FK ondelete should mirror model ('CASCADE'); AST shows {ondelete!r}"
    )


def test_orphan_rows_deleted_before_not_null_alter() -> None:
    """Step 2: ``DELETE FROM ppenorm WHERE hazard_id IS NULL`` must precede
    the alter_column to NOT NULL so Postgres doesn't trip on stale rows.
    """
    tree = _migration_tree()
    upgrade = _upgrade_fn(tree)
    execute_calls = _calls_named(upgrade, "execute")
    sql_texts: list[str] = []
    for call in execute_calls:
        if call.args and isinstance(call.args[0], ast.Constant) and isinstance(call.args[0].value, str):
            sql_texts.append(call.args[0].value)
    assert any(
        "delete from ppenorm" in t.lower() and "hazard_id is null" in t.lower()
        for t in sql_texts
    ), f"expected DELETE FROM ppenorm WHERE hazard_id IS NULL; saw {sql_texts!r}"


def test_alter_column_to_not_null_present() -> None:
    """Step 3: alter_column hazard_id to nullable=False."""
    tree = _migration_tree()
    upgrade = _upgrade_fn(tree)
    matching = [
        c for c in _calls_named(upgrade, "alter_column")
        if any(isinstance(a, ast.Constant) and a.value == "hazard_id" for a in c.args)
        and _keyword_value(c, "nullable") is False
    ]
    assert matching, (
        "expected alter_column(..., 'hazard_id', ..., nullable=False) "
        "to transition Step 1's nullable column to NOT NULL"
    )


def test_unique_constraint_matches_model_invariant() -> None:
    """Model ``__table_args__`` declares
    ``UniqueConstraint(tenant_id, position_id, hazard_id, item_name,
    name='uq_ppe_norm_position_hazard_item')``. Migration must mirror it
    so the DB enforces the same invariant.
    """
    tree = _migration_tree()
    upgrade = _upgrade_fn(tree)
    uc_calls = _calls_named(upgrade, "create_unique_constraint")
    found = False
    for call in uc_calls:
        if not call.args:
            continue
        name_arg = call.args[0]
        if not (isinstance(name_arg, ast.Constant) and name_arg.value == "uq_ppe_norm_position_hazard_item"):
            continue
        # Columns list — last positional arg is the columns list (when called
        # inside batch_op) OR penultimate when on op.create_unique_constraint.
        cols_arg = next(
            (a for a in reversed(call.args) if isinstance(a, ast.List)),
            None,
        )
        assert cols_arg is not None, "uq_ppe_norm_position_hazard_item must list columns"
        col_names = {
            elt.value for elt in cols_arg.elts
            if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
        }
        assert col_names == {"tenant_id", "position_id", "hazard_id", "item_name"}, (
            f"unique constraint columns mismatch: {col_names}"
        )
        found = True
    assert found, "missing create_unique_constraint('uq_ppe_norm_position_hazard_item', ...)"


def test_index_created_on_hazard_id() -> None:
    """Model declares ``index=True`` on hazard_id — migration must mirror."""
    tree = _migration_tree()
    upgrade = _upgrade_fn(tree)
    idx_calls = _calls_named(upgrade, "create_index")
    matching = [
        c for c in idx_calls
        if any(
            isinstance(a, ast.Constant) and a.value == "ix_ppenorm_hazard_id"
            for a in c.args
        )
    ]
    assert matching, "expected create_index('ix_ppenorm_hazard_id', 'ppenorm', ['hazard_id'])"


def test_downgrade_drops_hazard_id_column() -> None:
    """Downgrade reverses upgrade: drop unique constraint, drop index,
    drop column. Pinning the inverse keeps refactors honest.
    """
    tree = _migration_tree()
    downgrade = _downgrade_fn(tree)
    drop_columns = _calls_named(downgrade, "drop_column")
    matching = [
        c for c in drop_columns
        if any(isinstance(a, ast.Constant) and a.value == "hazard_id" for a in c.args)
    ]
    assert matching, "downgrade must drop_column('ppenorm', 'hazard_id')"


def test_downgrade_drops_unique_constraint_and_index() -> None:
    tree = _migration_tree()
    downgrade = _downgrade_fn(tree)

    constraint_drops = _calls_named(downgrade, "drop_constraint")
    constraint_names = {
        c.args[0].value for c in constraint_drops
        if c.args and isinstance(c.args[0], ast.Constant)
    }
    assert "uq_ppe_norm_position_hazard_item" in constraint_names, (
        f"downgrade must drop the unique constraint; saw {constraint_names}"
    )

    index_drops = _calls_named(downgrade, "drop_index")
    index_names = {
        c.args[0].value for c in index_drops
        if c.args and isinstance(c.args[0], ast.Constant)
    }
    assert "ix_ppenorm_hazard_id" in index_names, (
        f"downgrade must drop ix_ppenorm_hazard_id; saw {index_names}"
    )


def test_audit_credits_ppenorm_hazard_id_after_iter34() -> None:
    """Closed-loop verification: column_drift_lite must credit hazard_id
    once this migration is on the file system. Same pin shape as iter-32's
    ``test_audit_credits_iter32_columns``.
    """
    audit_path = REPO_ROOT / "scripts" / "audit" / "column_drift_lite.py"
    if not audit_path.exists():
        pytest.skip("column_drift_lite.py absent — pre-PR-#603 fork")
    import importlib.util as _ilu
    spec = _ilu.spec_from_file_location("column_drift_lite_iter34", audit_path)
    assert spec is not None and spec.loader is not None
    audit = _ilu.module_from_spec(spec)
    spec.loader.exec_module(audit)

    migration_cols = audit.collect_migration_columns()
    assert "hazard_id" in migration_cols.get("ppenorm", set()), (
        "audit doesn't credit ppenorm.hazard_id after iter-34 — closed-loop verify broken"
    )
