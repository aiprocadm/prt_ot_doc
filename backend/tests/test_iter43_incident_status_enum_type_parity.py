"""Pin tests for iter-43 incident.status enum type-parity migration.

Closes the type drift surfaced as out-of-scope by iter-42 — the
``incident.status`` column changes from migration's ``String(64)`` to
the model's ``Enum(IncidentStatus, name="incidentstatus")``.

Tests are pure AST (no app boot, no DB) — same Win+Py3.13-safe pattern
as iters 32/37/38/40/41/42.
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
    / "20260529_iter43_incident_status_enum_type_parity.py"
)

_INCIDENT_STATUS_VALUES = (
    "REPORTED", "INVESTIGATING", "ACTIONS", "CLOSED", "CANCELLED",
)


def _tree() -> ast.Module:
    return ast.parse(MIGRATION_PATH.read_text(encoding="utf-8"))


def _upgrade_fn(tree: ast.Module) -> ast.FunctionDef:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "upgrade":
            return node
    pytest.fail("upgrade() not found")


def _downgrade_fn(tree: ast.Module) -> ast.FunctionDef:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "downgrade":
            return node
    pytest.fail("downgrade() not found")


def _batch_alter_calls(fn: ast.FunctionDef, table: str) -> list[ast.With]:
    """All ``with op.batch_alter_table("<table>") as batch:`` blocks."""
    blocks: list[ast.With] = []
    for node in ast.walk(fn):
        if not isinstance(node, ast.With):
            continue
        for item in node.items:
            ctx = item.context_expr
            if (
                isinstance(ctx, ast.Call)
                and isinstance(ctx.func, ast.Attribute)
                and ctx.func.attr == "batch_alter_table"
                and ctx.args
                and isinstance(ctx.args[0], ast.Constant)
                and ctx.args[0].value == table
            ):
                blocks.append(node)
                break
    return blocks


def _alter_column_calls(block: ast.With, column: str) -> list[ast.Call]:
    """``batch_op.alter_column("col", ...)`` calls inside a With block."""
    calls: list[ast.Call] = []
    for node in ast.walk(block):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "alter_column"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and node.args[0].value == column
        ):
            calls.append(node)
    return calls


# ---------------------------------------------------------------------------
# Structural: revision chain + module constants.
# ---------------------------------------------------------------------------


def test_revision_chains_to_iter38() -> None:
    tree = _tree()
    revision_assigns = {
        a.target.id: a.value
        for a in tree.body
        if isinstance(a, ast.AnnAssign) and isinstance(a.target, ast.Name)
    }
    rev = revision_assigns.get("revision")
    down = revision_assigns.get("down_revision")
    assert isinstance(rev, ast.Constant) and rev.value == "20260529_iter43_incident_status_enum"
    assert isinstance(down, ast.Constant) and down.value == "20260529_iter38_server_default_c"


def test_incident_status_values_tuple_is_literal_and_correct() -> None:
    """The ``INCIDENT_STATUS_VALUES`` module constant must be a literal
    tuple of 5 strings, in the order that mirrors model:2267-2272.
    Brittle drift between model and migration would silently break the
    enum cast on PG. Spelled-out literal is required by the iter-42
    `_NEW_ENUMS` pin pattern + this iter's `enum_create_call` test
    (which relies on resolving Starred-of-Name → literal Tuple).
    """
    tree = _tree()
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and any(
                isinstance(t, ast.Name) and t.id == "INCIDENT_STATUS_VALUES"
                for t in node.targets
            )
        ):
            assert isinstance(node.value, ast.Tuple), (
                "INCIDENT_STATUS_VALUES must be a literal tuple, not an aliased Name"
            )
            actual = tuple(
                e.value for e in node.value.elts
                if isinstance(e, ast.Constant) and isinstance(e.value, str)
            )
            assert actual == _INCIDENT_STATUS_VALUES, (
                f"expected {_INCIDENT_STATUS_VALUES}, got {actual}"
            )
            return
    pytest.fail("INCIDENT_STATUS_VALUES module constant missing")


# ---------------------------------------------------------------------------
# Upgrade: enum creation + alter_column shape.
# ---------------------------------------------------------------------------


def test_upgrade_creates_incidentstatus_enum_before_alter_column() -> None:
    """The enum's `.create(op.get_bind(), checkfirst=True)` call must
    appear in source order BEFORE the alter_column that references it."""
    tree = _tree()
    upgrade = _upgrade_fn(tree)
    enum_create_lineno: int | None = None
    alter_lineno: int | None = None
    for node in ast.walk(upgrade):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "create"
        ):
            # Look for sa.Enum(...).create or var-named-enum.create
            caller = node.func.value
            if (
                isinstance(caller, ast.Call)
                and isinstance(caller.func, ast.Attribute)
                and caller.func.attr == "Enum"
            ) or (
                isinstance(caller, ast.Name)
            ):
                enum_create_lineno = node.lineno
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "alter_column"
        ):
            alter_lineno = alter_lineno or node.lineno
    assert enum_create_lineno is not None, (
        "upgrade missing enum.create(op.get_bind(), ...) call"
    )
    assert alter_lineno is not None, "upgrade missing alter_column call"
    assert enum_create_lineno < alter_lineno, (
        f"enum.create (line {enum_create_lineno}) must precede "
        f"alter_column (line {alter_lineno})"
    )


def test_upgrade_uses_batch_alter_table_for_incident() -> None:
    """SQLite portability requires batch_alter_table for column type change."""
    tree = _tree()
    upgrade = _upgrade_fn(tree)
    blocks = _batch_alter_calls(upgrade, "incident")
    assert len(blocks) == 1, (
        f"expected exactly 1 batch_alter_table('incident'), got {len(blocks)}"
    )


def test_upgrade_alter_column_status_changes_type_to_enum() -> None:
    """alter_column('status', existing_type=String(64), type_=Enum(...))"""
    tree = _tree()
    upgrade = _upgrade_fn(tree)
    block = _batch_alter_calls(upgrade, "incident")[0]
    calls = _alter_column_calls(block, "status")
    assert calls, "no batch_op.alter_column('status', ...) in upgrade batch block"
    call = calls[0]
    kw_map = {kw.arg: kw.value for kw in call.keywords}
    # existing_type must be sa.String(length=64)
    existing = kw_map.get("existing_type")
    assert isinstance(existing, ast.Call), "existing_type must be sa.String(...)"
    assert (
        isinstance(existing.func, ast.Attribute) and existing.func.attr == "String"
    ), f"existing_type expected sa.String, got {ast.dump(existing.func)}"
    # type_ must be sa.Enum(...) (or a Name binding to one)
    type_ = kw_map.get("type_")
    assert type_ is not None, "alter_column missing type_= kwarg"
    # Accept either inline sa.Enum(...) or Name resolved to one.
    if isinstance(type_, ast.Call):
        assert (
            isinstance(type_.func, ast.Attribute) and type_.func.attr in ("Enum", "ENUM")
        ), f"type_ expected sa.Enum/postgresql.ENUM, got {ast.dump(type_.func)}"
    elif isinstance(type_, ast.Name):
        # Verify the binding is to sa.Enum(...).
        for stmt in ast.walk(upgrade):
            if (
                isinstance(stmt, ast.Assign)
                and any(
                    isinstance(t, ast.Name) and t.id == type_.id for t in stmt.targets
                )
                and isinstance(stmt.value, ast.Call)
                and isinstance(stmt.value.func, ast.Attribute)
                and stmt.value.func.attr in ("Enum", "ENUM")
            ):
                break
        else:
            pytest.fail(f"type_=`{type_.id}` not bound to sa.Enum(...) in upgrade")
    else:
        pytest.fail(f"type_ unexpected node: {ast.dump(type_)}")


def test_upgrade_alter_column_status_preserves_nullable_false() -> None:
    """existing_nullable=False — status must remain NOT NULL."""
    tree = _tree()
    upgrade = _upgrade_fn(tree)
    block = _batch_alter_calls(upgrade, "incident")[0]
    call = _alter_column_calls(block, "status")[0]
    kw_map = {kw.arg: kw.value for kw in call.keywords}
    existing_nullable = kw_map.get("existing_nullable")
    assert isinstance(existing_nullable, ast.Constant) and existing_nullable.value is False, (
        f"existing_nullable expected False, got {ast.dump(existing_nullable) if existing_nullable else 'missing'}"
    )


def test_upgrade_alter_column_status_provides_postgresql_using() -> None:
    """postgresql_using kwarg must be present for PG cast (ignored on SQLite)."""
    tree = _tree()
    upgrade = _upgrade_fn(tree)
    block = _batch_alter_calls(upgrade, "incident")[0]
    call = _alter_column_calls(block, "status")[0]
    kw_map = {kw.arg: kw.value for kw in call.keywords}
    pg_using = kw_map.get("postgresql_using")
    assert isinstance(pg_using, ast.Constant) and isinstance(pg_using.value, str), (
        "postgresql_using must be a string constant"
    )
    # The text should reference the incidentstatus enum.
    assert "incidentstatus" in pg_using.value, (
        f"postgresql_using={pg_using.value!r} must cast to incidentstatus"
    )


# ---------------------------------------------------------------------------
# Downgrade: inverse alter + enum drop.
# ---------------------------------------------------------------------------


def test_downgrade_uses_batch_alter_table() -> None:
    tree = _tree()
    downgrade = _downgrade_fn(tree)
    blocks = _batch_alter_calls(downgrade, "incident")
    assert len(blocks) == 1


def test_downgrade_alter_column_reverts_type_to_string_64() -> None:
    """alter_column reverts type_ back to sa.String(length=64)."""
    tree = _tree()
    downgrade = _downgrade_fn(tree)
    block = _batch_alter_calls(downgrade, "incident")[0]
    calls = _alter_column_calls(block, "status")
    assert calls
    call = calls[0]
    kw_map = {kw.arg: kw.value for kw in call.keywords}
    type_ = kw_map.get("type_")
    assert isinstance(type_, ast.Call), "type_ must be sa.String(...)"
    assert (
        isinstance(type_.func, ast.Attribute) and type_.func.attr == "String"
    ), f"type_ expected sa.String, got {ast.dump(type_.func)}"


def test_downgrade_drops_incidentstatus_enum() -> None:
    """sa.Enum(name="incidentstatus").drop(op.get_bind(), checkfirst=True)"""
    tree = _tree()
    downgrade = _downgrade_fn(tree)
    for node in ast.walk(downgrade):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "drop"
        ):
            continue
        caller = node.func.value
        if not (
            isinstance(caller, ast.Call)
            and isinstance(caller.func, ast.Attribute)
            and caller.func.attr == "Enum"
        ):
            continue
        for kw in caller.keywords:
            if (
                kw.arg == "name"
                and isinstance(kw.value, ast.Constant)
                and kw.value.value == "incidentstatus"
            ):
                return
    pytest.fail("downgrade missing sa.Enum(name='incidentstatus').drop(...) call")


def test_downgrade_drops_enum_after_alter_column() -> None:
    """Enum drop must come AFTER alter_column reverts the col type — can't
    drop the type while a col still references it."""
    tree = _tree()
    downgrade = _downgrade_fn(tree)
    alter_lineno: int | None = None
    enum_drop_lineno: int | None = None
    for node in ast.walk(downgrade):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "alter_column"
        ):
            alter_lineno = alter_lineno or node.lineno
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "drop"
        ):
            caller = node.func.value
            if (
                isinstance(caller, ast.Call)
                and isinstance(caller.func, ast.Attribute)
                and caller.func.attr == "Enum"
            ):
                enum_drop_lineno = node.lineno
    assert alter_lineno is not None
    assert enum_drop_lineno is not None
    assert alter_lineno < enum_drop_lineno, (
        f"alter_column (line {alter_lineno}) must precede enum.drop "
        f"(line {enum_drop_lineno}) — can't drop the type while col references it"
    )
