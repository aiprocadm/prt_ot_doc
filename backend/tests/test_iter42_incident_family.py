"""Pin tests for iter-42 incident-family cohort migration.

Closes the FINAL 3 column_drift_lite business-drift tables (Session 85
baseline minus iters 39/40/41 closures):
  - incident (alter): +6 cols + 7 indexes.
  - incident_log (create_table): 6 business cols + 2 new PG enums.
  - incident_person (create_table): 3 cols + 1 new PG enum + UC + 4 indexes.

Plus 5 new PG enums (incidenttype, incidentstage, incidentpersonrole,
incidentlogstage, incidentlogstatus).

Tests are pure AST + audit-integration (no full app boot) so they run on
Win+Py3.13 without the conftest crash.
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
    / "20260529_iter42_incident_family.py"
)

# (column, nullable, fk_target, ondelete, has_server_default).
# Mirrors iter-32 cohort tuple shape. Specifies the 6 added cols.
_INCIDENT_ADD_COLS: list[tuple[str, bool, str | None, str | None, bool]] = [
    ("company_id", False, "company.id", None, False),
    ("site_id", False, "site.id", None, False),
    ("incident_type", False, None, None, True),  # Enum, server_default=ACCIDENT
    ("investigation_stage", False, None, None, True),  # Enum, server_default=REGISTRATION
    ("location_description", True, None, None, False),
    ("pack_id", True, "document_pack.id", "SET NULL", False),
]

_INCIDENT_NEW_INDEXES: set[str] = {
    "ix_incident_company_id",
    "ix_incident_site_id",
    "ix_incident_pack_id",
    "ix_incident_company",
    "ix_incident_site",
    "ix_incident_status",
    "ix_incident_occurred_at",
}

# (column, sa_type_attr, nullable).
_INCIDENT_LOG_COHORT: list[tuple[str, str, bool]] = [
    ("id", "String", False),
    ("tenant_id", "String", False),
    ("incident_id", "String", False),
    ("author_id", "String", True),
    ("stage", "ENUM", False),
    ("status", "ENUM", False),
    ("message", "Text", False),
    ("metadata_json", "JSON", False),
    ("created_at", "DateTime", False),
    ("updated_at", "DateTime", False),
    ("version", "Integer", False),
]

_INCIDENT_LOG_BUSINESS_COLS = {"incident_id", "author_id", "stage", "status", "message", "metadata_json"}

_INCIDENT_LOG_INDEXES: set[str] = {
    "ix_incident_log_tenant_id",
    "ix_incident_log_incident_id",
    "ix_incident_log_author_id",
    "ix_incident_log_incident",
    "ix_incident_log_stage",
}

# (column, sa_type_attr, nullable).
_INCIDENT_PERSON_COHORT: list[tuple[str, str, bool]] = [
    ("id", "String", False),
    ("tenant_id", "String", False),
    ("incident_id", "String", False),
    ("person_id", "String", False),
    ("role", "Enum", False),
    ("created_at", "DateTime", False),
    ("updated_at", "DateTime", False),
    ("version", "Integer", False),
]

_INCIDENT_PERSON_BUSINESS_COLS = {"incident_id", "person_id", "role"}

_INCIDENT_PERSON_INDEXES: set[str] = {
    "ix_incident_person_tenant_id",
    "ix_incident_person_incident_id",
    "ix_incident_person_person_id",
    "ix_incident_person_role",
}

# 5 new PG enums created by iter-42 (existing incidentseverity NOT in scope).
_NEW_ENUMS: list[tuple[str, tuple[str, ...]]] = [
    ("incidenttype", ("ACCIDENT", "MICROTRAUMA", "NEAR_MISS", "UNSAFE_CONDITION")),
    ("incidentstage", ("REGISTRATION", "INVESTIGATION", "ACTION_PLAN", "FOLLOW_UP", "CLOSED")),
    ("incidentpersonrole", ("VICTIM", "WITNESS", "PARTICIPANT")),
    ("incidentlogstage", ("REGISTRATION", "INVESTIGATION", "ACTION_PLAN", "FOLLOW_UP", "CLOSED")),
    ("incidentlogstatus", ("REPORTED", "INVESTIGATING", "ACTIONS", "CLOSED", "CANCELLED")),
]


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


def _add_column_calls(fn: ast.FunctionDef, table: str) -> list[ast.Call]:
    calls: list[ast.Call] = []
    for node in ast.walk(fn):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "add_column"
            and len(node.args) >= 2
            and isinstance(node.args[0], ast.Constant)
            and node.args[0].value == table
        ):
            calls.append(node)
    return calls


def _column_call_for(table: str, column: str, fn: ast.FunctionDef) -> ast.Call:
    for call in _add_column_calls(fn, table):
        col_arg = call.args[1]
        if (
            isinstance(col_arg, ast.Call)
            and col_arg.args
            and isinstance(col_arg.args[0], ast.Constant)
            and col_arg.args[0].value == column
        ):
            return col_arg
    pytest.fail(f"add_column({table!r}, sa.Column({column!r}, ...)) not in upgrade()")


def _create_table_calls(fn: ast.FunctionDef, table: str) -> list[ast.Call]:
    calls: list[ast.Call] = []
    for node in ast.walk(fn):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "create_table"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and node.args[0].value == table
        ):
            calls.append(node)
    return calls


def _column_in_create_table(create_call: ast.Call, column: str) -> ast.Call | None:
    for arg in create_call.args[1:]:
        if not (
            isinstance(arg, ast.Call)
            and isinstance(arg.func, ast.Attribute)
            and arg.func.attr == "Column"
        ):
            continue
        if (
            arg.args
            and isinstance(arg.args[0], ast.Constant)
            and arg.args[0].value == column
        ):
            return arg
    return None


def _sa_type_of(col_call: ast.Call) -> str | None:
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


def _index_names(fn: ast.FunctionDef, table: str) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(fn):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "create_index"
            and len(node.args) >= 3
        ):
            continue
        idx_arg = node.args[0]
        idx_name: str | None = None
        if isinstance(idx_arg, ast.Constant) and isinstance(idx_arg.value, str):
            idx_name = idx_arg.value
        elif (
            isinstance(idx_arg, ast.Call)
            and isinstance(idx_arg.func, ast.Attribute)
            and idx_arg.func.attr == "f"
            and idx_arg.args
            and isinstance(idx_arg.args[0], ast.Constant)
        ):
            idx_name = idx_arg.args[0].value
        if idx_name is None:
            continue
        table_arg = node.args[1]
        if isinstance(table_arg, ast.Constant) and table_arg.value == table:
            found.add(idx_name)
    return found


# ---------------------------------------------------------------------------
# Structural: revision chain.
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
    assert isinstance(rev, ast.Constant) and rev.value == "20260529_iter42_incident_family"
    assert isinstance(down, ast.Constant) and down.value == "20260529_iter38_server_default_c"


# ---------------------------------------------------------------------------
# incident (alter): 6 cols + 7 indexes.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("column", "_n", "_fk", "_od", "_sd"), _INCIDENT_ADD_COLS)
def test_incident_alter_adds_column(
    column: str, _n: bool, _fk: str | None, _od: str | None, _sd: bool,
) -> None:
    tree = _tree()
    upgrade = _upgrade_fn(tree)
    _column_call_for("incident", column, upgrade)  # raises if missing


@pytest.mark.parametrize(("column", "nullable", "_fk", "_od", "_sd"), _INCIDENT_ADD_COLS)
def test_incident_alter_column_nullable_matches(
    column: str, nullable: bool, _fk: str | None, _od: str | None, _sd: bool,
) -> None:
    tree = _tree()
    upgrade = _upgrade_fn(tree)
    col_call = _column_call_for("incident", column, upgrade)
    nullable_kw = None
    for kw in col_call.keywords:
        if kw.arg == "nullable" and isinstance(kw.value, ast.Constant):
            nullable_kw = kw.value.value
    assert nullable_kw is nullable, (
        f"incident.{column}: expected nullable={nullable}, got {nullable_kw!r}"
    )


@pytest.mark.parametrize(("column", "_n", "fk_target", "ondelete", "_sd"), _INCIDENT_ADD_COLS)
def test_incident_alter_column_fk_target_matches(
    column: str, _n: bool, fk_target: str | None, ondelete: str | None, _sd: bool,
) -> None:
    tree = _tree()
    upgrade = _upgrade_fn(tree)
    col_call = _column_call_for("incident", column, upgrade)
    fk_args = [
        arg for arg in col_call.args
        if isinstance(arg, ast.Call)
        and isinstance(arg.func, ast.Attribute)
        and arg.func.attr == "ForeignKey"
    ]
    if fk_target is None:
        assert not fk_args, f"incident.{column}: unexpected ForeignKey"
        return
    assert fk_args, f"incident.{column}: expected FK to {fk_target}"
    target = fk_args[0].args[0]
    assert isinstance(target, ast.Constant) and target.value == fk_target
    ondelete_kw = None
    for kw in fk_args[0].keywords:
        if kw.arg == "ondelete" and isinstance(kw.value, ast.Constant):
            ondelete_kw = kw.value.value
    assert ondelete_kw == ondelete, (
        f"incident.{column}: expected ondelete={ondelete}, got {ondelete_kw!r}"
    )


@pytest.mark.parametrize(("column", "_n", "_fk", "_od", "has_default"), _INCIDENT_ADD_COLS)
def test_incident_alter_column_server_default_when_expected(
    column: str, _n: bool, _fk: str | None, _od: str | None, has_default: bool,
) -> None:
    tree = _tree()
    upgrade = _upgrade_fn(tree)
    col_call = _column_call_for("incident", column, upgrade)
    has_kw = any(kw.arg == "server_default" for kw in col_call.keywords)
    assert has_kw is has_default, (
        f"incident.{column}: expected server_default present={has_default}, got {has_kw}"
    )


def test_incident_alter_creates_all_new_indexes() -> None:
    tree = _tree()
    upgrade = _upgrade_fn(tree)
    found = _index_names(upgrade, "incident")
    missing = _INCIDENT_NEW_INDEXES - found
    assert not missing, f"incident missing indexes: {sorted(missing)}"


def test_incident_alter_cohort_size_pinned_at_six() -> None:
    tree = _tree()
    upgrade = _upgrade_fn(tree)
    assert len(_add_column_calls(upgrade, "incident")) == len(_INCIDENT_ADD_COLS)


# ---------------------------------------------------------------------------
# incident_log (create_table).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("column", "_sa", "_n"), _INCIDENT_LOG_COHORT)
def test_incident_log_create_table_has_column(column: str, _sa: str, _n: bool) -> None:
    tree = _tree()
    upgrade = _upgrade_fn(tree)
    create_calls = _create_table_calls(upgrade, "incident_log")
    assert create_calls, "no create_table('incident_log')"
    assert _column_in_create_table(create_calls[0], column) is not None, (
        f"incident_log.{column} missing"
    )


@pytest.mark.parametrize(("column", "sa_type", "_n"), _INCIDENT_LOG_COHORT)
def test_incident_log_create_table_column_sa_type(
    column: str, sa_type: str, _n: bool,
) -> None:
    tree = _tree()
    upgrade = _upgrade_fn(tree)
    create_calls = _create_table_calls(upgrade, "incident_log")
    col_call = _column_in_create_table(create_calls[0], column)
    assert col_call is not None
    actual = _sa_type_of(col_call)
    assert actual == sa_type, (
        f"incident_log.{column}: expected sa.{sa_type}, got sa.{actual}"
    )


@pytest.mark.parametrize(("column", "_sa", "nullable"), _INCIDENT_LOG_COHORT)
def test_incident_log_create_table_column_nullable(
    column: str, _sa: str, nullable: bool,
) -> None:
    tree = _tree()
    upgrade = _upgrade_fn(tree)
    create_calls = _create_table_calls(upgrade, "incident_log")
    col_call = _column_in_create_table(create_calls[0], column)
    assert col_call is not None
    nullable_kw = None
    for kw in col_call.keywords:
        if kw.arg == "nullable" and isinstance(kw.value, ast.Constant):
            nullable_kw = kw.value.value
    assert nullable_kw is nullable


def test_incident_log_create_table_creates_all_expected_indexes() -> None:
    tree = _tree()
    upgrade = _upgrade_fn(tree)
    found = _index_names(upgrade, "incident_log")
    missing = _INCIDENT_LOG_INDEXES - found
    assert not missing, f"incident_log missing indexes: {sorted(missing)}"


def test_incident_log_incident_fk_has_cascade_ondelete() -> None:
    """incident_log.incident_id FK must have ondelete=CASCADE to mirror model."""
    tree = _tree()
    upgrade = _upgrade_fn(tree)
    create_calls = _create_table_calls(upgrade, "incident_log")
    for arg in create_calls[0].args[1:]:
        if not (
            isinstance(arg, ast.Call)
            and isinstance(arg.func, ast.Attribute)
            and arg.func.attr == "ForeignKeyConstraint"
            and len(arg.args) >= 2
        ):
            continue
        local = arg.args[0]
        target = arg.args[1]
        if not (isinstance(local, ast.List) and isinstance(target, ast.List)):
            continue
        local_names = [
            e.value for e in local.elts
            if isinstance(e, ast.Constant) and isinstance(e.value, str)
        ]
        target_names = [
            e.value for e in target.elts
            if isinstance(e, ast.Constant) and isinstance(e.value, str)
        ]
        if local_names == ["incident_id"] and target_names == ["incident.id"]:
            ondelete_kw = None
            for kw in arg.keywords:
                if kw.arg == "ondelete" and isinstance(kw.value, ast.Constant):
                    ondelete_kw = kw.value.value
            assert ondelete_kw == "CASCADE", (
                f"incident_log.incident_id: expected ondelete=CASCADE, got {ondelete_kw!r}"
            )
            return
    pytest.fail("incident_log.incident_id FK constraint missing")


# ---------------------------------------------------------------------------
# incident_person (create_table) + UC.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("column", "_sa", "_n"), _INCIDENT_PERSON_COHORT)
def test_incident_person_create_table_has_column(column: str, _sa: str, _n: bool) -> None:
    tree = _tree()
    upgrade = _upgrade_fn(tree)
    create_calls = _create_table_calls(upgrade, "incident_person")
    assert create_calls
    assert _column_in_create_table(create_calls[0], column) is not None


def test_incident_person_creates_all_expected_indexes() -> None:
    tree = _tree()
    upgrade = _upgrade_fn(tree)
    found = _index_names(upgrade, "incident_person")
    missing = _INCIDENT_PERSON_INDEXES - found
    assert not missing, f"incident_person missing indexes: {sorted(missing)}"


def test_incident_person_unique_constraint_present() -> None:
    """UniqueConstraint(tenant_id, incident_id, person_id, role,
    name="uq_incident_person_role") inside create_table."""
    tree = _tree()
    upgrade = _upgrade_fn(tree)
    create_calls = _create_table_calls(upgrade, "incident_person")
    for arg in create_calls[0].args[1:]:
        if not (
            isinstance(arg, ast.Call)
            and isinstance(arg.func, ast.Attribute)
            and arg.func.attr == "UniqueConstraint"
        ):
            continue
        cols = [
            a.value for a in arg.args
            if isinstance(a, ast.Constant) and isinstance(a.value, str)
        ]
        name_kw = None
        for kw in arg.keywords:
            if kw.arg == "name" and isinstance(kw.value, ast.Constant):
                name_kw = kw.value.value
        if (
            cols == ["tenant_id", "incident_id", "person_id", "role"]
            and name_kw == "uq_incident_person_role"
        ):
            return
    pytest.fail(
        "incident_person create_table missing UniqueConstraint("
        "tenant_id, incident_id, person_id, role, name='uq_incident_person_role')"
    )


def test_incident_person_role_has_victim_server_default() -> None:
    """role: Enum(IncidentPersonRole) NOT NULL default=VICTIM in model →
    server_default='VICTIM' in migration (iter-38 pattern for enum defaults)."""
    tree = _tree()
    upgrade = _upgrade_fn(tree)
    create_calls = _create_table_calls(upgrade, "incident_person")
    col_call = _column_in_create_table(create_calls[0], "role")
    assert col_call is not None
    sd_kw = None
    for kw in col_call.keywords:
        if kw.arg == "server_default" and isinstance(kw.value, ast.Constant):
            sd_kw = kw.value.value
    assert sd_kw == "VICTIM", (
        f"incident_person.role: expected server_default='VICTIM', got {sd_kw!r}"
    )


# ---------------------------------------------------------------------------
# Enum creation: 5 new PG enums.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("enum_name", "expected_values"), _NEW_ENUMS)
def test_new_pg_enum_declared_with_expected_values(
    enum_name: str, expected_values: tuple[str, ...],
) -> None:
    """Each new enum appears as ``sa.Enum(*<VALUES>, name="<enum_name>")``
    in at least one column declaration. We pin only the name+values; the
    column that hosts it is checked elsewhere.
    """
    tree = _tree()
    upgrade = _upgrade_fn(tree)
    for node in ast.walk(upgrade):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in ("Enum", "ENUM")
        ):
            continue
        name_kw = None
        for kw in node.keywords:
            if kw.arg == "name" and isinstance(kw.value, ast.Constant):
                name_kw = kw.value.value
        if name_kw != enum_name:
            continue
        # Check positional args are the expected values. They may also be
        # a Starred reference to a module-level constant — accept that too.
        positional = node.args
        if len(positional) == 1 and isinstance(positional[0], ast.Starred):
            # Starred unpacking from a module-level constant — check the
            # module constant value.
            starred_arg = positional[0].value
            if isinstance(starred_arg, ast.Name):
                # Find the module-level assignment.
                for top in tree.body:
                    if (
                        isinstance(top, ast.Assign)
                        and any(isinstance(t, ast.Name) and t.id == starred_arg.id for t in top.targets)
                    ):
                        if isinstance(top.value, ast.Tuple):
                            actual = tuple(
                                e.value for e in top.value.elts
                                if isinstance(e, ast.Constant) and isinstance(e.value, str)
                            )
                            assert actual == expected_values, (
                                f"enum {enum_name}: expected {expected_values}, got {actual}"
                            )
                            return
        # Plain positional case.
        actual = tuple(
            a.value for a in positional
            if isinstance(a, ast.Constant) and isinstance(a.value, str)
        )
        if actual == expected_values:
            return
    pytest.fail(
        f"enum {enum_name!r} not declared with values {expected_values} in upgrade"
    )


# ---------------------------------------------------------------------------
# Downgrade: enum drops + table drops.
# ---------------------------------------------------------------------------


def test_downgrade_drops_all_new_enums() -> None:
    """Each of the 5 new enums must be dropped in downgrade via
    ``sa.Enum(name=X).drop(...)``."""
    tree = _tree()
    downgrade = _downgrade_fn(tree)
    found: set[str] = set()
    for node in ast.walk(downgrade):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "drop"
        ):
            continue
        # Need: caller is sa.Enum(name="X")
        caller = node.func.value
        if not (
            isinstance(caller, ast.Call)
            and isinstance(caller.func, ast.Attribute)
            and caller.func.attr == "Enum"
        ):
            continue
        for kw in caller.keywords:
            if kw.arg == "name" and isinstance(kw.value, ast.Constant):
                found.add(kw.value.value)
    expected = {name for name, _values in _NEW_ENUMS}
    missing = expected - found
    assert not missing, f"downgrade missing enum drops: {sorted(missing)}"


def test_downgrade_drops_incident_log_and_incident_person_tables() -> None:
    tree = _tree()
    downgrade = _downgrade_fn(tree)
    dropped_tables: set[str] = set()
    for node in ast.walk(downgrade):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "drop_table"
            and node.args
            and isinstance(node.args[0], ast.Constant)
        ):
            dropped_tables.add(node.args[0].value)
    assert "incident_log" in dropped_tables
    assert "incident_person" in dropped_tables


def test_downgrade_drops_all_added_incident_columns() -> None:
    """Each upgrade add_column on incident must have a matching drop_column."""
    tree = _tree()
    upgrade = _upgrade_fn(tree)
    downgrade = _downgrade_fn(tree)
    added = set()
    for call in _add_column_calls(upgrade, "incident"):
        if (
            len(call.args) >= 2
            and isinstance(call.args[1], ast.Call)
            and call.args[1].args
            and isinstance(call.args[1].args[0], ast.Constant)
        ):
            added.add(call.args[1].args[0].value)
    dropped = set()
    for node in ast.walk(downgrade):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "drop_column"
            and len(node.args) >= 2
            and isinstance(node.args[0], ast.Constant)
            and node.args[0].value == "incident"
            and isinstance(node.args[1], ast.Constant)
        ):
            dropped.add(node.args[1].value)
    assert added == dropped, (
        f"incident col symmetry broken: added-only={added - dropped}, "
        f"dropped-only={dropped - added}"
    )


# ---------------------------------------------------------------------------
# Closed-loop audit integration.
# ---------------------------------------------------------------------------


def _load_audit():
    audit_path = REPO_ROOT / "scripts" / "audit" / "column_drift_lite.py"
    spec = importlib.util.spec_from_file_location("column_drift_lite", audit_path)
    assert spec is not None and spec.loader is not None
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)
    return audit


def test_audit_credits_incident_new_business_cols() -> None:
    audit = _load_audit()
    migration_cols = audit.collect_migration_columns()
    credited = migration_cols.get("incident", set())
    expected_cols = {
        "company_id", "site_id", "incident_type",
        "investigation_stage", "location_description", "pack_id",
    }
    missing = expected_cols - credited
    assert not missing, (
        f"audit doesn't credit {sorted(missing)} for incident after iter-42; "
        f"credited={sorted(credited)}"
    )


def test_audit_credits_incident_log_business_cols() -> None:
    audit = _load_audit()
    migration_cols = audit.collect_migration_columns()
    credited = migration_cols.get("incident_log", set())
    missing = _INCIDENT_LOG_BUSINESS_COLS - credited
    assert not missing, (
        f"audit doesn't credit {sorted(missing)} for incident_log after iter-42; "
        f"credited={sorted(credited)}"
    )


def test_audit_credits_incident_person_business_cols() -> None:
    audit = _load_audit()
    migration_cols = audit.collect_migration_columns()
    credited = migration_cols.get("incident_person", set())
    missing = _INCIDENT_PERSON_BUSINESS_COLS - credited
    assert not missing, (
        f"audit doesn't credit {sorted(missing)} for incident_person after iter-42; "
        f"credited={sorted(credited)}"
    )


def test_audit_drift_incident_family_cleared_after_iter42() -> None:
    """The incident family (3 tables) drops out of business-drift after iter-42.
    Other tables (npabinding, training_certificates, journalentry) MAY still
    be flagged on this branch because iters 39/40/41 are on parallel branches —
    subset assertion handles either ordering."""
    audit = _load_audit()
    models = audit.find_versioned_models()
    migration_cols = audit.collect_migration_columns()
    drift = audit.compute_drift(models, migration_cols)
    drift_tables = {info.tablename for info, _missing in drift}
    incident_family = {"incident", "incident_log", "incident_person"}
    assert not (incident_family & drift_tables), (
        f"incident family should be cleared; still flagged: "
        f"{sorted(incident_family & drift_tables)}"
    )
