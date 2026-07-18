"""Pin tests for iter-48 ``outbox_events`` model-col closure migration.

Closes the LAST business-drift table surfaced by ``column_drift_lite``
(Session 96 candidate, the final one). The ``OutboxEvent`` model
(``backend/app/models/job_engine.py``) declares a ``last_error`` column that
no migration ever created::

    last_error    Text    nullable

The table is created by ``20260222_next10`` (event_type / event_id / payload /
status / attempts / next_attempt_at + base) and later altered by
``20260314_next43_outbox_webhooks_spine`` (aggregate_type / aggregate_id /
headers / sent_at). Neither adds ``last_error`` — yet the column is live: the
outbox service writes it on delivery failure and the admin diagnostics route
reads it. On PostgreSQL (the ``alembic upgrade`` path) any write touching it
raises ``UndefinedColumnError`` — real drift (option a), not a rename or
intentional design. (The older *singular* ``outbox`` table has its own
``last_error`` via ``20250305_add_outbox_delivery_metadata`` — a DISTINCT
legacy table; this migration concerns only the plural ``outbox_events``.)

Simplest variant in the whole drift cohort: a single NULLABLE ``Text`` column.
So unlike iter-47/iter-42 there is:
  * NO ``server_default`` — nullable cols never violate a constraint on
    existing rows (no backfill, zero data risk; contrast iter-35's NOT NULL
    ``riskmap.company_id`` which needed a data backfill).
  * NO enum type — plain ``sa.Text()``, so no ``CREATE TYPE`` / RB-002 guard.
  * NO index — the model declares none on ``last_error``.

Ordering: ``outbox_events`` is created by ``20260222_next10``, which is a
verified ancestor of every head — it sits on the main ``next`` backbone
(next10 -> ... -> next43 -> ... -> next50) that ``20260416_next69_merge_heads``
collapses into a single ancestor of the entire ``iter`` cohort. So
``down_revision = iter38`` alone orders this migration correctly under
``alembic upgrade heads``; there are no cross-branch FK targets, so unlike
iter-46 it needs **no** ``depends_on`` (mirrors iter-47).

After iter-48 lands the lightweight audit's broadest scope reaches **0
business-drift / 0 critical** — the capstone of the drift defect class.

Tests are pure AST + audit-integration (no full app boot) so they run on
Win+Py3.13 without the conftest crash. Mirrors the iter-47 pin-test.
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
    / "20260529_iter48_outbox_events_last_error.py"
)

_REVISION = "20260529_iter48_outbox_events_last_error"
_DOWN_REVISION = "20260529_iter38_server_default_c"

_TABLE = "outbox_events"
_COLUMN = "last_error"


def _migration_tree() -> ast.Module:
    return ast.parse(MIGRATION_PATH.read_text(encoding="utf-8"))


def _upgrade_fn(tree: ast.Module) -> ast.FunctionDef:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "upgrade":
            return node
    pytest.fail("upgrade() not found in iter-48 migration")


def _downgrade_fn(tree: ast.Module) -> ast.FunctionDef:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "downgrade":
            return node
    pytest.fail("downgrade() not found in iter-48 migration")


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


def _module_values(tree: ast.Module) -> dict[str, ast.expr]:
    """Module-level name -> value AST, handling BOTH ``x = ...`` (Assign) and
    ``x: T = ...`` (AnnAssign). The versions dir mixes both styles."""
    out: dict[str, ast.expr] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    out[target.id] = node.value
        elif (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.value is not None
        ):
            out[node.target.id] = node.value
    return out


# ---------------------------------------------------------------------------
# Revision graph + dependency edges.
# ---------------------------------------------------------------------------


def test_migration_revision_chains_to_iter38() -> None:
    values = _module_values(_migration_tree())
    rev = values.get("revision")
    down = values.get("down_revision")
    assert isinstance(rev, ast.Constant) and rev.value == _REVISION
    assert isinstance(down, ast.Constant) and down.value == _DOWN_REVISION


def test_migration_declares_no_depends_on() -> None:
    """``outbox_events`` is created by ``20260222_next10`` — a verified ancestor
    of every head via ``next69_merge_heads`` — and ``last_error`` has no FK. So
    ``down_revision`` alone orders this migration correctly under ``alembic
    upgrade heads``; ``depends_on`` must be None. Pin it so nobody adds a
    spurious edge (or assumes one is needed)."""
    values = _module_values(_migration_tree())
    deps = values.get("depends_on")
    assert isinstance(deps, ast.Constant) and deps.value is None, (
        f"depends_on must be None (no cross-branch targets), AST shows {ast.dump(deps)}"
        if deps is not None
        else "depends_on assignment is missing"
    )


# ---------------------------------------------------------------------------
# Column shape (presence, nullability, type, no server_default).
# ---------------------------------------------------------------------------


def test_last_error_present_in_upgrade() -> None:
    upgrade = _upgrade_fn(_migration_tree())
    _column_call_for(_COLUMN, upgrade)  # raises pytest.fail if missing


def test_last_error_is_nullable() -> None:
    """The model declares ``mapped_column(Text, nullable=True)`` — the migration
    must match. Nullable is what makes this a zero-risk add (no backfill)."""
    upgrade = _upgrade_fn(_migration_tree())
    col_call = _column_call_for(_COLUMN, upgrade)
    nullable_kw = None
    for kw in col_call.keywords:
        if kw.arg == "nullable" and isinstance(kw.value, ast.Constant):
            nullable_kw = kw.value.value
    assert nullable_kw is True, (
        f"{_TABLE}.{_COLUMN}: expected nullable=True, AST shows {nullable_kw!r}"
    )


def test_last_error_has_no_server_default() -> None:
    """A nullable col must NOT declare a ``server_default`` — existing rows are
    satisfied by NULL, and the model has no server-side default. (Contrast
    iter-42/47 NOT NULL cols, which require one.)"""
    upgrade = _upgrade_fn(_migration_tree())
    col_call = _column_call_for(_COLUMN, upgrade)
    sd_value: ast.expr | None = None
    for kw in col_call.keywords:
        if kw.arg == "server_default":
            sd_value = kw.value
    assert sd_value is None, (
        f"{_TABLE}.{_COLUMN}: nullable col must not declare server_default, "
        f"AST shows {ast.dump(sd_value)}"
    )


def test_last_error_type_is_text() -> None:
    """Type arg must be ``sa.Text()`` — matching the model's ``Mapped[str | None]
    = mapped_column(Text, ...)``. Pinning this also documents the absence of an
    enum type (no RB-002 concern, no CREATE TYPE)."""
    upgrade = _upgrade_fn(_migration_tree())
    col_call = _column_call_for(_COLUMN, upgrade)
    assert len(col_call.args) >= 2, f"{_TABLE}.{_COLUMN}: sa.Column has no type arg"
    type_arg = col_call.args[1]
    assert (
        isinstance(type_arg, ast.Call)
        and isinstance(type_arg.func, ast.Attribute)
        and type_arg.func.attr == "Text"
    ), f"{_TABLE}.{_COLUMN}: type arg must be sa.Text(), got {ast.dump(type_arg)}"


# ---------------------------------------------------------------------------
# No incidental DDL: no new table, no index, single add_column.
# ---------------------------------------------------------------------------


def test_no_create_table_in_upgrade() -> None:
    """iter-48 only adds one column to the existing ``outbox_events`` table —
    no new tables."""
    upgrade = _upgrade_fn(_migration_tree())
    for node in ast.walk(upgrade):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "create_table"
        ):
            pytest.fail("unexpected op.create_table call in iter-48 upgrade")


def test_upgrade_adds_no_index() -> None:
    """The model declares no index on ``last_error`` (none in its
    ``__table_args__``), so the migration must add none either."""
    upgrade = _upgrade_fn(_migration_tree())
    for node in ast.walk(upgrade):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "create_index"
        ):
            pytest.fail("unexpected op.create_index call in iter-48 upgrade")


def test_only_one_add_column() -> None:
    """Exactly one add_column, to ``outbox_events``. Pin the cohort size at 1 so
    a future stray col forces a conscious test update."""
    upgrade = _upgrade_fn(_migration_tree())
    adds = _add_column_calls(upgrade)
    assert len(adds) == 1, f"expected exactly 1 add_column, found {[t for t, _ in adds]}"
    assert adds[0][0] == _TABLE, f"add_column target must be {_TABLE!r}, got {adds[0][0]!r}"


def test_upgrade_and_downgrade_symmetric() -> None:
    """The single upgrade add_column has a matching downgrade drop_column."""
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
    assert upgrade_cols == downgrade_cols == {(_TABLE, _COLUMN)}, (
        f"col symmetry broken: upgrade={upgrade_cols}, downgrade={downgrade_cols}"
    )


# ---------------------------------------------------------------------------
# Closed-loop: the lightweight audit must credit the col and clear the drift.
# ---------------------------------------------------------------------------


def _load_audit():
    audit_path = REPO_ROOT / "scripts" / "audit" / "column_drift_lite.py"
    spec = importlib.util.spec_from_file_location("column_drift_lite", audit_path)
    assert spec is not None and spec.loader is not None
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)
    return audit


def test_audit_credits_iter48_last_error() -> None:
    """Closed-loop: after iter-48 ships, ``column_drift_lite`` credits
    ``last_error`` to the ``outbox_events`` table."""
    audit = _load_audit()
    credited = audit.collect_migration_columns().get(_TABLE, set())
    assert _COLUMN in credited, (
        f"audit doesn't credit {_TABLE}.{_COLUMN} after iter-48 — "
        f"closed-loop broken (credited={sorted(credited)})"
    )


def test_audit_drift_outbox_events_cleared_after_iter48() -> None:
    """Closed-loop: ``outbox_events`` must no longer appear in the drift list."""
    audit = _load_audit()
    models = audit.find_versioned_models()
    migration_cols = audit.collect_migration_columns()
    drift = audit.compute_drift(models, migration_cols)
    drift_tables = {info.tablename for info, _missing in drift}
    assert _TABLE not in drift_tables, "outbox_events should be cleared by iter-48"


def test_audit_business_drift_reaches_zero() -> None:
    """Capstone milestone: iter-48 is the LAST business-drift table, so after it
    ships the lightweight audit's broadest scope is 0 business-drift / 0
    critical (absent) tables. This is intentionally GLOBAL — if a future change
    re-introduces drift, this canary fails with the offending tables named, and
    the maintainer updates it deliberately."""
    audit = _load_audit()
    models = audit.find_versioned_models()
    migration_cols = audit.collect_migration_columns()
    drift = audit.compute_drift(models, migration_cols)
    assert drift == [], (
        "business-drift not zero after iter-48: "
        f"{[(info.tablename, sorted(missing)) for info, missing in drift]}"
    )
    absent = [info.tablename for info in models.values() if info.tablename not in migration_cols]
    assert absent == [], f"critical absent tables present: {sorted(absent)}"
