"""Pin tests for iter-41 journalentry concept-resolution migration.

Closes 1 of the 5 column_drift_lite business-drift tables (Session 85
baseline). The migration drops the old generic event-log shape created
by initial_schema and recreates ``journalentry`` with the current model
shape (safety-briefing entry).

Tests are pure AST + audit-integration (no full app boot) so they run on
Win+Py3.13 without the conftest crash. Different from iter-32/iter-40
cohort pattern (column add) — iter-41 is concept-replacement, so the
structural tests pin a different shape (drop+create vs add_column).
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
    / "20260529_iter41_journalentry_concept_resolution.py"
)

_TABLE = "journalentry"

# Tuple of (column, sa_type_attr, nullable). sa_type_attr is the AST-level
# attribute name in `sa.X`/`sa.X(...)`: e.g. "String", "Enum", "Date".
_NEW_SHAPE_COHORT: list[tuple[str, str, bool]] = [
    ("id", "String", False),
    ("tenant_id", "String", False),
    ("journal_id", "String", False),
    ("person_id", "String", False),
    ("entry_type", "Enum", False),
    ("entry_date", "Date", False),
    ("instructor", "String", True),
    ("notes", "Text", True),
    ("metadata_json", "JSON", False),
    ("deleted_at", "DateTime", True),
    ("created_at", "DateTime", False),
    ("updated_at", "DateTime", False),
    ("version", "Integer", False),
]

# Model business cols (subset of _NEW_SHAPE_COHORT, sans mixins) that
# the closed-loop audit check expects to find credited.
_MODEL_BUSINESS_COLS = {
    "journal_id", "person_id", "entry_type", "entry_date",
    "instructor", "notes", "metadata_json",
}

# Cols that MUST NOT appear in the upgrade's new create_table (old shape).
_OLD_SHAPE_BANNED_IN_UPGRADE = {"payload", "occurred_at"}

# Expected FKs in upgrade's create_table: (col, target).
_EXPECTED_FKS: list[tuple[str, str]] = [
    ("tenant_id", "tenant.id"),
    ("journal_id", "journal.id"),
    ("person_id", "person.id"),
]

# Expected indexes (idx_name, cols).
_EXPECTED_INDEXES: list[tuple[str, list[str]]] = [
    ("ix_journalentry_tenant_id", ["tenant_id"]),
    ("ix_journalentry_journal_id", ["journal_id"]),
    ("ix_journalentry_person_id", ["person_id"]),
    ("ix_journal_entry_type", ["tenant_id", "entry_type"]),
]


def _migration_tree() -> ast.Module:
    return ast.parse(MIGRATION_PATH.read_text(encoding="utf-8"))


def _upgrade_fn(tree: ast.Module) -> ast.FunctionDef:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "upgrade":
            return node
    pytest.fail("upgrade() not found in iter-41 migration")


def _downgrade_fn(tree: ast.Module) -> ast.FunctionDef:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "downgrade":
            return node
    pytest.fail("downgrade() not found in iter-41 migration")


def _create_table_calls(fn: ast.FunctionDef, tablename: str) -> list[ast.Call]:
    """All ``op.create_table("<tablename>", ...)`` calls in the function."""
    calls: list[ast.Call] = []
    for node in ast.walk(fn):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "create_table"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and node.args[0].value == tablename
        ):
            calls.append(node)
    return calls


def _drop_table_calls(fn: ast.FunctionDef, tablename: str) -> list[ast.Call]:
    """All ``op.drop_table("<tablename>")`` calls in the function."""
    calls: list[ast.Call] = []
    for node in ast.walk(fn):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "drop_table"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and node.args[0].value == tablename
        ):
            calls.append(node)
    return calls


def _column_call_in_create_table(create_call: ast.Call, column: str) -> ast.Call | None:
    """Locate the ``sa.Column("col", ...)`` inside a create_table call."""
    for arg in create_call.args[1:]:
        if not isinstance(arg, ast.Call):
            continue
        if not (
            isinstance(arg.func, ast.Attribute) and arg.func.attr == "Column"
        ):
            continue
        if (
            arg.args
            and isinstance(arg.args[0], ast.Constant)
            and arg.args[0].value == column
        ):
            return arg
    return None


def _sa_type_attr_of(col_call: ast.Call) -> str | None:
    """For ``sa.Column("c", sa.X(...))``: return ``"X"``. For ``sa.Column("c", sa.X)``:
    return ``"X"``. None if undecodable.
    """
    if len(col_call.args) < 2:
        return None
    second = col_call.args[1]
    if isinstance(second, ast.Call):
        f = second.func
        if isinstance(f, ast.Attribute):
            return f.attr
        if isinstance(f, ast.Name):
            return f.id
    if isinstance(second, ast.Attribute):
        return second.attr
    if isinstance(second, ast.Name):
        return second.id
    return None


# ---------------------------------------------------------------------------
# Structural: revision chain + drop/create sequence.
# ---------------------------------------------------------------------------


def test_migration_revision_chains_to_iter38() -> None:
    tree = _migration_tree()
    revision_assigns = {
        a.target.id: a.value
        for a in tree.body
        if isinstance(a, ast.AnnAssign) and isinstance(a.target, ast.Name)
    }
    rev = revision_assigns.get("revision")
    down = revision_assigns.get("down_revision")
    assert isinstance(rev, ast.Constant) and rev.value == "20260529_iter41_journalentry_concept"
    assert isinstance(down, ast.Constant) and down.value == "20260529_iter38_server_default_c"


def test_upgrade_drops_old_journalentry_before_recreating() -> None:
    """The upgrade must drop_table the old shape, then create_table the new."""
    tree = _migration_tree()
    upgrade = _upgrade_fn(tree)
    drops = _drop_table_calls(upgrade, _TABLE)
    creates = _create_table_calls(upgrade, _TABLE)
    assert len(drops) == 1, f"expected exactly 1 drop_table({_TABLE!r}), got {len(drops)}"
    assert len(creates) == 1, f"expected exactly 1 create_table({_TABLE!r}), got {len(creates)}"
    # Source-order: drop_table line < create_table line (proxy for ordering).
    assert drops[0].lineno < creates[0].lineno, (
        "drop_table must appear before create_table in upgrade source"
    )


def test_downgrade_drops_new_shape_then_recreates_old_shape() -> None:
    """Symmetric: downgrade drops the new table then recreates the old shape."""
    tree = _migration_tree()
    downgrade = _downgrade_fn(tree)
    drops = _drop_table_calls(downgrade, _TABLE)
    creates = _create_table_calls(downgrade, _TABLE)
    assert len(drops) == 1, "expected exactly 1 drop_table in downgrade"
    assert len(creates) == 1, "expected exactly 1 create_table in downgrade"
    assert drops[0].lineno < creates[0].lineno


# ---------------------------------------------------------------------------
# Upgrade create_table shape pin.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("column", "_sa_type", "_nullable"), _NEW_SHAPE_COHORT)
def test_upgrade_create_table_includes_column(
    column: str, _sa_type: str, _nullable: bool,
) -> None:
    tree = _migration_tree()
    upgrade = _upgrade_fn(tree)
    create_calls = _create_table_calls(upgrade, _TABLE)
    assert create_calls, f"no create_table({_TABLE!r}) in upgrade"
    col_call = _column_call_in_create_table(create_calls[0], column)
    assert col_call is not None, (
        f"upgrade create_table missing column {column!r}"
    )


@pytest.mark.parametrize(("column", "sa_type", "_nullable"), _NEW_SHAPE_COHORT)
def test_upgrade_create_table_column_has_expected_sa_type(
    column: str, sa_type: str, _nullable: bool,
) -> None:
    tree = _migration_tree()
    upgrade = _upgrade_fn(tree)
    create_calls = _create_table_calls(upgrade, _TABLE)
    col_call = _column_call_in_create_table(create_calls[0], column)
    assert col_call is not None
    actual = _sa_type_attr_of(col_call)
    assert actual == sa_type, (
        f"{_TABLE}.{column}: expected sa.{sa_type}, AST shows sa.{actual}"
    )


@pytest.mark.parametrize(("column", "_sa_type", "nullable"), _NEW_SHAPE_COHORT)
def test_upgrade_create_table_column_nullable_matches_spec(
    column: str, _sa_type: str, nullable: bool,
) -> None:
    tree = _migration_tree()
    upgrade = _upgrade_fn(tree)
    create_calls = _create_table_calls(upgrade, _TABLE)
    col_call = _column_call_in_create_table(create_calls[0], column)
    assert col_call is not None
    nullable_kw = None
    for kw in col_call.keywords:
        if kw.arg == "nullable" and isinstance(kw.value, ast.Constant):
            nullable_kw = kw.value.value
    assert nullable_kw is nullable, (
        f"{_TABLE}.{column}: expected nullable={nullable}, AST shows {nullable_kw!r}"
    )


@pytest.mark.parametrize("banned_col", sorted(_OLD_SHAPE_BANNED_IN_UPGRADE))
def test_upgrade_create_table_does_not_carry_old_shape_columns(banned_col: str) -> None:
    """The new shape must not include payload / occurred_at (old generic shape).
    Regression guard against accidental copy-paste from initial_schema."""
    tree = _migration_tree()
    upgrade = _upgrade_fn(tree)
    create_calls = _create_table_calls(upgrade, _TABLE)
    assert create_calls
    assert _column_call_in_create_table(create_calls[0], banned_col) is None, (
        f"upgrade create_table must NOT carry old-shape column {banned_col!r}"
    )


def test_upgrade_entry_type_column_uses_journaltype_enum_create_false() -> None:
    """``entry_type`` must use ``sa.Enum(..., name="journaltype", create_type=False)``
    to reuse the PG enum type created by iter-24 — re-creating it would
    fail with "type journaltype already exists" on PostgreSQL.
    """
    tree = _migration_tree()
    upgrade = _upgrade_fn(tree)
    create_calls = _create_table_calls(upgrade, _TABLE)
    col_call = _column_call_in_create_table(create_calls[0], "entry_type")
    assert col_call is not None
    enum_call = col_call.args[1]
    assert isinstance(enum_call, ast.Call)
    assert isinstance(enum_call.func, ast.Attribute)
    assert enum_call.func.attr == "Enum"
    kw_map = {kw.arg: kw.value for kw in enum_call.keywords}
    name_kw = kw_map.get("name")
    create_kw = kw_map.get("create_type")
    assert isinstance(name_kw, ast.Constant) and name_kw.value == "journaltype"
    assert isinstance(create_kw, ast.Constant) and create_kw.value is False, (
        "entry_type Enum must have create_type=False (journaltype enum already "
        "created by iter-24)"
    )


# ---------------------------------------------------------------------------
# Foreign keys.
# ---------------------------------------------------------------------------


def _foreign_key_constraint_calls(create_call: ast.Call) -> list[ast.Call]:
    """All ``sa.ForeignKeyConstraint([cols], [targets], ...)`` inside a create_table."""
    fks: list[ast.Call] = []
    for arg in create_call.args[1:]:
        if (
            isinstance(arg, ast.Call)
            and isinstance(arg.func, ast.Attribute)
            and arg.func.attr == "ForeignKeyConstraint"
        ):
            fks.append(arg)
    return fks


@pytest.mark.parametrize(("col", "target"), _EXPECTED_FKS)
def test_upgrade_foreign_key_present_for_col(col: str, target: str) -> None:
    tree = _migration_tree()
    upgrade = _upgrade_fn(tree)
    create_calls = _create_table_calls(upgrade, _TABLE)
    fks = _foreign_key_constraint_calls(create_calls[0])
    matched = False
    for fk in fks:
        if len(fk.args) < 2:
            continue
        local_cols = fk.args[0]
        target_cols = fk.args[1]
        if not (isinstance(local_cols, ast.List) and isinstance(target_cols, ast.List)):
            continue
        local_names = [
            elt.value for elt in local_cols.elts
            if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
        ]
        target_names = [
            elt.value for elt in target_cols.elts
            if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
        ]
        if local_names == [col] and target_names == [target]:
            matched = True
            break
    assert matched, (
        f"upgrade create_table missing ForeignKeyConstraint([{col}], [{target}])"
    )


# ---------------------------------------------------------------------------
# Unique constraint.
# ---------------------------------------------------------------------------


def test_upgrade_unique_constraint_present() -> None:
    """``UniqueConstraint(tenant_id, journal_id, person_id, entry_type, entry_date,
    name="uq_journal_entry_unique_person_date")`` must be declared inside the
    create_table — matches the model's ``__table_args__``."""
    tree = _migration_tree()
    upgrade = _upgrade_fn(tree)
    create_calls = _create_table_calls(upgrade, _TABLE)
    for arg in create_calls[0].args[1:]:
        if not (
            isinstance(arg, ast.Call)
            and isinstance(arg.func, ast.Attribute)
            and arg.func.attr == "UniqueConstraint"
        ):
            continue
        # Args are positional string literals (col names); kwarg name=...
        cols = [
            a.value for a in arg.args
            if isinstance(a, ast.Constant) and isinstance(a.value, str)
        ]
        name_kw = None
        for kw in arg.keywords:
            if kw.arg == "name" and isinstance(kw.value, ast.Constant):
                name_kw = kw.value.value
        if (
            cols == ["tenant_id", "journal_id", "person_id", "entry_type", "entry_date"]
            and name_kw == "uq_journal_entry_unique_person_date"
        ):
            return
    pytest.fail(
        "upgrade create_table missing UniqueConstraint("
        "tenant_id, journal_id, person_id, entry_type, entry_date, "
        "name='uq_journal_entry_unique_person_date')"
    )


# ---------------------------------------------------------------------------
# Indexes.
# ---------------------------------------------------------------------------


def test_upgrade_creates_all_expected_indexes() -> None:
    tree = _migration_tree()
    upgrade = _upgrade_fn(tree)
    found: dict[str, list[str]] = {}
    for node in ast.walk(upgrade):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "create_index"
            and len(node.args) >= 3
        ):
            continue
        idx_name_node, table_node, cols_node = node.args[0], node.args[1], node.args[2]
        # idx_name may be op.f("ix_...") wrapping or plain "ix_..."
        idx_name: str | None = None
        if isinstance(idx_name_node, ast.Constant) and isinstance(idx_name_node.value, str):
            idx_name = idx_name_node.value
        elif (
            isinstance(idx_name_node, ast.Call)
            and isinstance(idx_name_node.func, ast.Attribute)
            and idx_name_node.func.attr == "f"
            and idx_name_node.args
            and isinstance(idx_name_node.args[0], ast.Constant)
            and isinstance(idx_name_node.args[0].value, str)
        ):
            idx_name = idx_name_node.args[0].value
        if idx_name is None:
            continue
        if not (isinstance(table_node, ast.Constant) and table_node.value == _TABLE):
            continue
        if not isinstance(cols_node, ast.List):
            continue
        col_names = [
            elt.value for elt in cols_node.elts
            if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
        ]
        found[idx_name] = col_names
    for idx_name, expected_cols in _EXPECTED_INDEXES:
        assert idx_name in found, f"missing create_index({idx_name!r}, {_TABLE!r}, ...)"
        assert found[idx_name] == expected_cols, (
            f"{idx_name}: cols expected {expected_cols}, AST shows {found[idx_name]}"
        )


# ---------------------------------------------------------------------------
# Closed-loop audit integration.
# ---------------------------------------------------------------------------


def test_audit_credits_iter41_model_business_columns() -> None:
    """After iter-41, ``column_drift_lite`` credits all 7 model business cols
    to journalentry. The drop_table+create_table union semantics mean the
    audit sees the union of old and new shapes — model_business ⊆ union."""
    audit_path = REPO_ROOT / "scripts" / "audit" / "column_drift_lite.py"
    spec = importlib.util.spec_from_file_location("column_drift_lite", audit_path)
    assert spec is not None and spec.loader is not None
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)

    migration_cols = audit.collect_migration_columns()
    credited = migration_cols.get(_TABLE, set())
    missing = _MODEL_BUSINESS_COLS - credited
    assert not missing, (
        f"audit doesn't credit {sorted(missing)} for {_TABLE} after iter-41 — "
        f"closed-loop broken (credited={sorted(credited)})"
    )


def test_audit_drift_journalentry_cleared_after_iter41() -> None:
    """Closed-loop count: journalentry must drop out of the business-drift list."""
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
        f"{_TABLE} should be cleared by iter-41; still in drift: "
        f"{sorted({info.tablename: sorted(missing) for info, missing in drift if info.tablename == _TABLE})}"
    )
    # Incident family stays design-blocked.
    design_blocked = {"incident", "incident_log", "incident_person"}
    assert design_blocked <= drift_tables, (
        f"Expected design-blocked tables {sorted(design_blocked)} still flagged; "
        f"got {sorted(drift_tables)}"
    )
