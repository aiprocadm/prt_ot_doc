"""Pin tests for iter-38 server_default parity cohort migration (Subset C).

Closes the final 33-col cohort of server_default drift surfaced by
``scripts/audit/server_default_parity.py`` (iter-36 audit):

  * 32 columns declared as ``mapped_column(Enum(EnumClass[, name=...]))``
    with ``default=EnumClass.MEMBER`` — server_default = UPPER_CASE
    member name (SA's default native_enum=True PG storage convention).
  * 1 column ``tenant.kind`` declared as
    ``mapped_column(Enum("customer", "branch", "contractor",
    name="tenantkind"))`` with ``default="customer"`` (literal lowercase)
    — server_default = "customer".

Combined with iter-37 (Subset A+B, 19 cols), this closes the entire
server_default parity drift class. The audit's drift count goes from
33 → 0 after this iter.

Tests are pure AST + closed-loop audit run (no full app boot) so they
run on Win+Py3.13 without the conftest crash. Mirrors iter-37's test
shape exactly.
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
    / "20260529_iter38_server_default_cohort_c.py"
)
AUDIT_PATH = REPO_ROOT / "scripts" / "audit" / "server_default_parity.py"


# Tuple of (table, column, sa_type_name, sa_type_arg_or_none, default_unparsed_source).
# Same shape as iter-37's _COHORT_AB: ``default_unparsed_source`` is what
# ``ast.unparse`` returns for the ``server_default=`` kwarg's AST value,
# i.e. ``repr()``-style single-quoted source ("'MEDIUM'", "'customer'").
# Alphabetically sorted by (table, column) — matches migration ordering.
_COHORT_C: list[tuple[str, str, str, str | int | None, str]] = [
    ("approval_instance_steps", "status", "String", 64, "'PENDING'"),
    ("approval_instances", "status", "String", 64, "'DRAFT'"),
    ("approval_processes", "status", "String", 64, "'pending'"),
    ("approval_route_steps", "step_type", "String", 64, "'APPROVE'"),
    ("approval_tasks", "status", "String", 64, "'open'"),
    ("attestation", "status", "String", 64, "'active'"),
    ("client_request_tickets", "status", "String", 64, "'open'"),
    ("edo_envelopes", "status", "String", 64, "'queued'"),
    ("equipment", "status", "String", 64, "'ACTIVE'"),
    ("idempotency_keys", "status", "String", 64, "'PENDING'"),
    ("incident", "severity", "String", 64, "'MEDIUM'"),
    ("incident", "status", "String", 64, "'REPORTED'"),
    ("inspection_prescription", "status", "String", 64, "'open'"),
    ("npa", "status", "String", 64, "'ACTIVE'"),
    ("pack_run_items", "status", "String", 64, "'queued'"),
    ("pack_runs", "status", "String", 64, "'queued'"),
    ("package_preset_items", "output_format", "String", 64, "'both'"),
    ("package_preset_items", "replace_mode", "String", 64, "'none'"),
    ("package_presets_v2", "source_type", "String", 64, "'csv'"),
    ("package_presets_v2", "status", "String", 64, "'draft'"),
    ("package_profiles_v2", "status", "String", 64, "'draft'"),
    ("package_requirements", "status", "String", 64, "'missing'"),
    ("package_requirements", "type", "String", 64, "'file'"),
    ("package_runs", "status", "String", 64, "'draft'"),
    ("permit", "status", "String", 64, "'ACTIVE'"),
    ("pipeline_runs", "status", "String", 64, "'QUEUED'"),
    ("plantask", "status", "String", 64, "'OPEN'"),
    ("ppeissue", "status", "String", 64, "'ISSUED'"),
    ("ppeitem", "category", "String", 64, "'other'"),
    ("template", "status", "String", 64, "'DRAFT'"),
    ("templateversion", "status", "String", 64, "'UPLOADED'"),
    ("tenant", "kind", "String", 64, "'customer'"),
    ("training_session", "status", "String", 64, "'scheduled'"),
]


def _migration_tree() -> ast.Module:
    return ast.parse(MIGRATION_PATH.read_text(encoding="utf-8"))


def _function(tree: ast.Module, name: str) -> ast.FunctionDef:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    pytest.fail(f"{name}() not found in iter-38 migration")


def _alter_column_calls(fn: ast.FunctionDef) -> list[ast.Call]:
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


def test_migration_revision_chains_to_iter37() -> None:
    tree = _migration_tree()
    revision_assigns = {
        a.target.id: a.value
        for a in tree.body
        if isinstance(a, ast.AnnAssign) and isinstance(a.target, ast.Name)
    }
    rev = revision_assigns.get("revision")
    down = revision_assigns.get("down_revision")
    assert (
        isinstance(rev, ast.Constant) and rev.value == "20260529_iter38_server_default_c"
    ), f"revision = {getattr(rev, 'value', None)!r}"
    assert (
        isinstance(down, ast.Constant) and down.value == "20260529_iter37_server_default_ab"
    ), f"down_revision = {getattr(down, 'value', None)!r}"


def test_cohort_size_pinned_at_thirtythree() -> None:
    """Adding/removing a column from this cohort requires also updating _COHORT_C."""
    tree = _migration_tree()
    upgrade = _function(tree, "upgrade")
    assert len(_alter_column_calls(upgrade)) == len(_COHORT_C) == 33


def test_no_create_table_in_upgrade() -> None:
    """iter-38 only alters existing columns — no new tables/columns."""
    tree = _migration_tree()
    upgrade = _function(tree, "upgrade")
    for node in ast.walk(upgrade):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in {"create_table", "add_column"}
        ):
            pytest.fail(f"unexpected op.{node.func.attr} call in iter-38 upgrade")


@pytest.mark.parametrize(("table", "column", "_sa_type", "_arg", "_default"), _COHORT_C)
def test_cohort_column_has_alter_column_in_upgrade(
    table: str, column: str, _sa_type: str, _arg: str | int | None, _default: str
) -> None:
    tree = _migration_tree()
    upgrade = _function(tree, "upgrade")
    _alter_for(table, column, upgrade)  # raises via pytest.fail if missing


@pytest.mark.parametrize(("table", "column", "sa_type", "_arg", "_default"), _COHORT_C)
def test_cohort_column_existing_type_present(
    table: str, column: str, sa_type: str, _arg: str | int | None, _default: str
) -> None:
    tree = _migration_tree()
    upgrade = _function(tree, "upgrade")
    call = _alter_for(table, column, upgrade)
    existing_type_src = _kw_value_source(call, "existing_type")
    assert existing_type_src is not None, f"{table}.{column}: missing existing_type= kwarg"
    assert (
        sa_type in existing_type_src
    ), f"{table}.{column}: existing_type={existing_type_src!r} does not mention {sa_type!r}"


@pytest.mark.parametrize(("table", "column", "_sa_type", "_arg", "_default"), _COHORT_C)
def test_cohort_column_existing_nullable_false(
    table: str, column: str, _sa_type: str, _arg: str | int | None, _default: str
) -> None:
    tree = _migration_tree()
    upgrade = _function(tree, "upgrade")
    call = _alter_for(table, column, upgrade)
    src = _kw_value_source(call, "existing_nullable")
    assert src == "False", f"{table}.{column}: existing_nullable={src!r}, expected 'False'"


@pytest.mark.parametrize(("table", "column", "_sa_type", "_arg", "default"), _COHORT_C)
def test_cohort_column_server_default_matches_model(
    table: str, column: str, _sa_type: str, _arg: str | int | None, default: str
) -> None:
    tree = _migration_tree()
    upgrade = _function(tree, "upgrade")
    call = _alter_for(table, column, upgrade)
    src = _kw_value_source(call, "server_default")
    assert (
        src == default
    ), f"{table}.{column}: server_default source = {src!r}, expected {default!r}"


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
# Closed-loop audit verification (final drift count = 0)
# ---------------------------------------------------------------------------


def _load_audit():
    spec = _ilu.spec_from_file_location("server_default_parity", AUDIT_PATH)
    assert spec is not None and spec.loader is not None
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_audit_no_longer_flags_thirtythree_cohort_cols() -> None:
    """After iter-38, every column in the Subset C cohort disappears from drift."""
    audit = _load_audit()
    drift = audit.run()
    flagged = {(t, c) for (t, c) in drift}
    for table, column, *_ in _COHORT_C:
        assert (table, column) not in flagged, (
            f"{table}.{column} still flagged by audit — alter_column credit broken or "
            f"migration missing this column"
        )


def test_audit_drift_total_count_is_zero() -> None:
    """The combined iter-37 + iter-38 closure means total drift = 0.

    This is the cumulative closed-loop assertion: server_default parity is
    fully achieved across the codebase. Any future regression (a new model
    field with ``nullable=False, default=<literal>`` missing a matching
    migration ``server_default``) will surface here.
    """
    audit = _load_audit()
    drift = audit.run()
    assert drift == {}, (
        f"unexpected server_default drift remaining: {len(drift)} cols "
        f"across {len({t for (t, _) in drift})} tables: "
        f"{sorted(drift.keys())}"
    )
