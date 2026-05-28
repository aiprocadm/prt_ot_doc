"""Pin tests for iter-35 riskmap.company_id NOT NULL FK backfill migration.

Closes the second of the two NOT-NULL FK items iter-32 deliberately deferred
(see iter-32 docstring line 30):

    riskmap:   company_id   (NOT NULL FK — no safe server_default)

Bug class: ORM-Migration drift, flavor (b) — column declared on the model
(``models.py::RiskMap.company_id``) but absent from the creator migration
(``6b6dee7c951f_initial_schema.py`` line 484 ``op.create_table('riskmap',
...)`` lists methodology_id/matrix/recalculated_at/tenant_id/... but no
company_id).

Strategy: mirrors iter-34's 3-step pattern.

    Step 1: ADD COLUMN company_id (nullable=True) + FK + index.
    Step 2: ``DELETE FROM riskmap WHERE company_id IS NULL``.
    Step 3: ``ALTER COLUMN company_id SET NOT NULL`` (batch_alter for SQLite).

Plus matching ``UniqueConstraint(tenant_id, company_id, site_id,
position_id, methodology_id, name='uq_riskmap_scope')`` per the model
``__table_args__``. All five columns exist after iter-32 (site_id /
position_id / document_pack_id added then; tenant_id / methodology_id
exist since initial; company_id added by this migration) — so the UC is
satisfiable only at the end of iter-35.

Tests are pure AST + module-spec inspection — no full app boot — so they
run on Win+Py3.13 without the conftest crash.
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
    / "20260529_iter35_riskmap_company_id_backfill.py"
)


def _migration_tree() -> ast.Module:
    if not MIGRATION_PATH.exists():
        pytest.fail(f"iter-35 migration not found at {MIGRATION_PATH}")
    return ast.parse(MIGRATION_PATH.read_text(encoding="utf-8"))


def _upgrade_fn(tree: ast.Module) -> ast.FunctionDef:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "upgrade":
            return node
    pytest.fail("upgrade() not found in iter-35 migration")


def _downgrade_fn(tree: ast.Module) -> ast.FunctionDef:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "downgrade":
            return node
    pytest.fail("downgrade() not found in iter-35 migration")


def _calls_named(fn: ast.FunctionDef, attr: str) -> list[ast.Call]:
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


def test_migration_revision_chains_to_iter34() -> None:
    """iter-35 follows iter-34 in the iter chain (iter-32 → iter-34 → iter-35)."""
    tree = _migration_tree()
    revision_assigns = {
        a.target.id: a.value
        for a in tree.body
        if isinstance(a, ast.AnnAssign) and isinstance(a.target, ast.Name)
    }
    rev = revision_assigns.get("revision")
    down = revision_assigns.get("down_revision")
    assert isinstance(rev, ast.Constant) and rev.value == "20260529_iter35_riskmap_company"
    assert isinstance(down, ast.Constant) and down.value == "20260529_iter34_ppenorm_hazard"


def test_company_id_column_added_to_riskmap() -> None:
    tree = _migration_tree()
    upgrade = _upgrade_fn(tree)
    _add_column_for("riskmap", "company_id", upgrade)


def test_company_id_initially_nullable_for_safe_backfill() -> None:
    tree = _migration_tree()
    upgrade = _upgrade_fn(tree)
    col_call = _add_column_for("riskmap", "company_id", upgrade)
    assert _keyword_value(col_call, "nullable") is True


def test_company_id_fk_targets_company_without_ondelete() -> None:
    """Model declares ``ForeignKey('company.id')`` with no ondelete — the
    migration FK must mirror that exactly (no spurious ondelete kwarg)."""
    tree = _migration_tree()
    upgrade = _upgrade_fn(tree)
    col_call = _add_column_for("riskmap", "company_id", upgrade)
    fk_calls = [
        arg for arg in col_call.args
        if isinstance(arg, ast.Call)
        and isinstance(arg.func, ast.Attribute)
        and arg.func.attr == "ForeignKey"
    ]
    assert fk_calls, "company_id must declare sa.ForeignKey(...) inline"
    fk = fk_calls[0]
    target = fk.args[0] if fk.args else None
    assert isinstance(target, ast.Constant) and target.value == "company.id"
    assert _keyword_value(fk, "ondelete") is None, (
        "model has no ondelete; migration FK shouldn't either"
    )


def test_orphan_rows_deleted_before_not_null_alter() -> None:
    tree = _migration_tree()
    upgrade = _upgrade_fn(tree)
    sql_texts: list[str] = []
    for call in _calls_named(upgrade, "execute"):
        if call.args and isinstance(call.args[0], ast.Constant) and isinstance(call.args[0].value, str):
            sql_texts.append(call.args[0].value)
    assert any(
        "delete from riskmap" in t.lower() and "company_id is null" in t.lower()
        for t in sql_texts
    ), f"expected DELETE FROM riskmap WHERE company_id IS NULL; saw {sql_texts!r}"


def test_alter_column_to_not_null_present() -> None:
    tree = _migration_tree()
    upgrade = _upgrade_fn(tree)
    matching = [
        c for c in _calls_named(upgrade, "alter_column")
        if any(isinstance(a, ast.Constant) and a.value == "company_id" for a in c.args)
        and _keyword_value(c, "nullable") is False
    ]
    assert matching, (
        "expected alter_column(..., 'company_id', ..., nullable=False)"
    )


def test_unique_constraint_matches_model_invariant() -> None:
    """Model ``__table_args__`` declares
    ``UniqueConstraint(tenant_id, company_id, site_id, position_id,
    methodology_id, name='uq_riskmap_scope')`` — DB must mirror.
    All five columns exist after iter-32 added site_id/position_id and
    iter-35 adds company_id.
    """
    tree = _migration_tree()
    upgrade = _upgrade_fn(tree)
    uc_calls = _calls_named(upgrade, "create_unique_constraint")
    found = False
    for call in uc_calls:
        if not call.args:
            continue
        name_arg = call.args[0]
        if not (isinstance(name_arg, ast.Constant) and name_arg.value == "uq_riskmap_scope"):
            continue
        cols_arg = next(
            (a for a in reversed(call.args) if isinstance(a, ast.List)),
            None,
        )
        assert cols_arg is not None, "uq_riskmap_scope must list columns"
        col_names = {
            elt.value for elt in cols_arg.elts
            if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
        }
        assert col_names == {"tenant_id", "company_id", "site_id", "position_id", "methodology_id"}, (
            f"uq_riskmap_scope columns mismatch: {col_names}"
        )
        found = True
    assert found, "missing create_unique_constraint('uq_riskmap_scope', ...)"


def test_index_created_on_company_id() -> None:
    tree = _migration_tree()
    upgrade = _upgrade_fn(tree)
    matching = [
        c for c in _calls_named(upgrade, "create_index")
        if any(
            isinstance(a, ast.Constant) and a.value == "ix_riskmap_company_id"
            for a in c.args
        )
    ]
    assert matching, "expected create_index('ix_riskmap_company_id', 'riskmap', ['company_id'])"


def test_downgrade_drops_company_id_column() -> None:
    tree = _migration_tree()
    downgrade = _downgrade_fn(tree)
    matching = [
        c for c in _calls_named(downgrade, "drop_column")
        if any(isinstance(a, ast.Constant) and a.value == "company_id" for a in c.args)
    ]
    assert matching, "downgrade must drop_column('riskmap', 'company_id')"


def test_downgrade_drops_unique_constraint_and_index() -> None:
    tree = _migration_tree()
    downgrade = _downgrade_fn(tree)

    constraint_names = {
        c.args[0].value for c in _calls_named(downgrade, "drop_constraint")
        if c.args and isinstance(c.args[0], ast.Constant)
    }
    assert "uq_riskmap_scope" in constraint_names, (
        f"downgrade must drop uq_riskmap_scope; saw {constraint_names}"
    )

    index_names = {
        c.args[0].value for c in _calls_named(downgrade, "drop_index")
        if c.args and isinstance(c.args[0], ast.Constant)
    }
    assert "ix_riskmap_company_id" in index_names, (
        f"downgrade must drop ix_riskmap_company_id; saw {index_names}"
    )


def test_audit_credits_riskmap_company_id_after_iter35() -> None:
    """Closed-loop verification: column_drift_lite must credit company_id."""
    audit_path = REPO_ROOT / "scripts" / "audit" / "column_drift_lite.py"
    if not audit_path.exists():
        pytest.skip("column_drift_lite.py absent")
    import importlib.util as _ilu
    spec = _ilu.spec_from_file_location("column_drift_lite_iter35", audit_path)
    assert spec is not None and spec.loader is not None
    audit = _ilu.module_from_spec(spec)
    spec.loader.exec_module(audit)

    migration_cols = audit.collect_migration_columns()
    assert "company_id" in migration_cols.get("riskmap", set()), (
        "audit doesn't credit riskmap.company_id after iter-35 — closed-loop verify broken"
    )
