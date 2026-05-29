"""Pin tests for iter-47 ``file`` model-col closure migration.

Closes the ``file`` business-drift table surfaced by ``column_drift_lite``
(Session 95 candidate #1). The legacy ``File`` model
(``backend/app/models/file.py``) grew **eight** columns over the
clamav/quarantine + pack/company build-out that no migration ever created:

    original_name      String(255)                       nullable
    kind               Enum(file_kind)        NOT NULL    server_default DOCUMENT
    company_id         String(36)                         nullable, indexed
    pack_id            String(36)                         nullable, indexed
    is_quarantined     Boolean                NOT NULL    server_default true
    scan_status        Enum(file_scan_status) NOT NULL    server_default PENDING
    clamav_signature   String(255)                        nullable
    clamav_scanned_at  DateTime(timezone=True)            nullable

The only migrations touching ``file`` are ``6b6dee7c951f_initial_schema``
(storage_key, sha256, size, mime, meta_json + base) and
``8d2c1a6c5e24_domain_normalization`` (bucket). Both predate the eight cols.

They are live read/written in production: ``app/modules/security/clamav.py``
writes ``scan_status / is_quarantined / clamav_signature / clamav_scanned_at``;
``app/api/routes/files.py`` constructs ``File(...)`` with ``kind / company_id``;
``app/modules/documents/packs.py`` filters ``scan_status == CLEAN``. On
PostgreSQL (``alembic upgrade`` path) these raise ``UndefinedColumnError`` —
real drift (option a), not a rename or intentional design. (``file`` singular
and ``files`` plural are DISTINCT coexisting tables — the plural domain lives
in ``app/modules/files/`` and is created by ``20260312_next41``; there is no
rename chain between them.)

RB-002 guard: ``kind`` / ``scan_status`` use ``SQLEnum(PyEnum)`` which persists
the member NAME (uppercase) not the ``str`` value (lowercase), because the
model sets no ``values_callable``. The migration therefore declares the enum
labels and ``server_default`` values in UPPERCASE — matching what
``Base.metadata.create_all`` emits on PG. Lowercase here would reintroduce the
RB-002 defect class.

Ordering: ``file`` is created by the universal root ``6b6dee7c951f`` (an
ancestor of every head) and the two enum types are self-created in this
migration via ``sa.Enum(...).create(checkfirst=True)``. There are no
cross-branch FK targets, so unlike iter-46 this migration needs **no**
``depends_on`` — ``down_revision = iter38`` alone orders it correctly under
``alembic upgrade heads``.

Tests are pure AST + audit-integration (no full app boot) so they run on
Win+Py3.13 without the conftest crash. Mirrors the iter-46 pin-test (PR #612).
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
    / "20260529_iter47_file_business_cols.py"
)

_REVISION = "20260529_iter47_file_business_cols"
_DOWN_REVISION = "20260529_iter38_server_default_c"

_TABLE = "file"

# UPPERCASE enum NAME labels (what SQLEnum(PyEnum) persists on PG when no
# values_callable is set) — order mirrors the Python enum member order.
_FILE_KIND_LABELS = ("TEMPLATE", "DOCUMENT", "ARCHIVE", "DRAFT", "ATTACHMENT", "OTHER")
_FILE_SCAN_STATUS_LABELS = ("PENDING", "IN_PROGRESS", "CLEAN", "INFECTED", "ERROR")

# Module-level value tuples the migration must declare (RB-002 guard checks
# they equal the uppercase labels above, in enum-member order).
_ENUM_VALUE_CONSTANTS: dict[str, tuple[str, ...]] = {
    "FILE_KIND_VALUES": _FILE_KIND_LABELS,
    "FILE_SCAN_STATUS_VALUES": _FILE_SCAN_STATUS_LABELS,
}

# Tuple of (column, nullable, server_default_spec, enum_name).
#   server_default_spec:
#     None              -> NO server_default kwarg (nullable col)
#     ("const", "X")    -> server_default=<string Constant "X"> (enum label)
#     ("call",  "true") -> server_default=sa.true()  (func name == "true")
#   enum_name is None for non-enum columns; else the PG enum type name.
_COHORT: list[tuple[str, bool, tuple[str, str] | None, str | None]] = [
    ("original_name", True, None, None),
    ("kind", False, ("const", "DOCUMENT"), "file_kind"),
    ("company_id", True, None, None),
    ("pack_id", True, None, None),
    ("is_quarantined", False, ("call", "true"), None),
    ("scan_status", False, ("const", "PENDING"), "file_scan_status"),
    ("clamav_signature", True, None, None),
    ("clamav_scanned_at", True, None, None),
]

# Indexes iter-47 must add. ix_file_storage_key / ix_file_sha256 already exist
# (initial_schema), so only the four involving NEW columns are added here.
#   ix_file_company_id / ix_file_pack_id   -> inline index=True on the cols
#   ix_file_kind / ix_file_pack            -> __table_args__ composite indexes
_EXPECTED_INDEXES: list[tuple[str, str, list[str]]] = [
    ("ix_file_company_id", "file", ["company_id"]),
    ("ix_file_pack_id", "file", ["pack_id"]),
    ("ix_file_kind", "file", ["tenant_id", "kind"]),
    ("ix_file_pack", "file", ["tenant_id", "pack_id"]),
]


def _migration_tree() -> ast.Module:
    return ast.parse(MIGRATION_PATH.read_text(encoding="utf-8"))


def _upgrade_fn(tree: ast.Module) -> ast.FunctionDef:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "upgrade":
            return node
    pytest.fail("upgrade() not found in iter-47 migration")


def _downgrade_fn(tree: ast.Module) -> ast.FunctionDef:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "downgrade":
            return node
    pytest.fail("downgrade() not found in iter-47 migration")


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
    ``x: T = ...`` (AnnAssign). The dir mixes both styles."""
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


def _string_tuple(node: ast.expr | None) -> tuple[str, ...] | None:
    """Return the string elements of a Tuple/List node, or None if not a
    homogeneous string sequence."""
    if not isinstance(node, (ast.Tuple, ast.List)):
        return None
    out: list[str] = []
    for elt in node.elts:
        if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
            out.append(elt.value)
        else:
            return None
    return tuple(out)


def _enum_lifecycle_names(
    fn: ast.FunctionDef, action: str, *, require_checkfirst: bool = True
) -> set[str]:
    """Names of enum types created/dropped via ``sa.Enum(..., name="X").<action>(
    ...)``. When ``require_checkfirst`` is True, only counts calls that pass
    ``checkfirst=True`` (the idempotent idiom from iter-42/43); when False,
    counts ANY such call (used to assert the absence of explicit creates)."""
    names: set[str] = set()
    for node in ast.walk(fn):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == action
        ):
            continue
        recv = node.func.value
        if not (
            isinstance(recv, ast.Call)
            and isinstance(recv.func, ast.Attribute)
            and recv.func.attr == "Enum"
        ):
            continue
        enum_name = None
        for kw in recv.keywords:
            if kw.arg == "name" and isinstance(kw.value, ast.Constant):
                enum_name = kw.value.value
        if enum_name is None:
            continue
        if require_checkfirst:
            checkfirst = any(
                kw.arg == "checkfirst"
                and isinstance(kw.value, ast.Constant)
                and kw.value.value is True
                for kw in node.keywords
            )
            if not checkfirst:
                continue
        names.add(enum_name)
    return names


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
    """``file`` is created by the universal root ``6b6dee7c951f`` (ancestor of
    every head) and the enum types are self-created here — there are no
    cross-branch FK targets. So ``down_revision`` alone orders this migration
    correctly under ``alembic upgrade heads`` and ``depends_on`` must be None.
    Pin it so nobody adds a spurious edge (or, worse, assumes one is needed)."""
    values = _module_values(_migration_tree())
    deps = values.get("depends_on")
    assert isinstance(deps, ast.Constant) and deps.value is None, (
        f"depends_on must be None (no cross-branch targets), AST shows {ast.dump(deps)}"
        if deps is not None
        else "depends_on assignment is missing"
    )


# ---------------------------------------------------------------------------
# Per-column shape (presence, nullability, server_default, enum type).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("column", "_nullable", "_sd", "_enum"), _COHORT)
def test_cohort_column_present_in_upgrade(
    column: str, _nullable: bool, _sd: object, _enum: str | None,
) -> None:
    upgrade = _upgrade_fn(_migration_tree())
    _column_call_for(column, upgrade)  # raises pytest.fail if missing


@pytest.mark.parametrize(("column", "nullable", "_sd", "_enum"), _COHORT)
def test_cohort_column_nullable_matches_spec(
    column: str, nullable: bool, _sd: object, _enum: str | None,
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


@pytest.mark.parametrize(("column", "_nullable", "server_default_spec", "_enum"), _COHORT)
def test_cohort_column_server_default_matches_spec(
    column: str, _nullable: bool, server_default_spec: tuple[str, str] | None, _enum: str | None,
) -> None:
    """NOT NULL cols added to an existing table MUST carry a server_default so
    existing rows satisfy the constraint (iter-42 precedent). Nullable cols
    must NOT declare one (matching the model's lack of a server-side default)."""
    upgrade = _upgrade_fn(_migration_tree())
    col_call = _column_call_for(column, upgrade)
    sd_value: ast.expr | None = None
    for kw in col_call.keywords:
        if kw.arg == "server_default":
            sd_value = kw.value
    if server_default_spec is None:
        assert sd_value is None, (
            f"{_TABLE}.{column}: nullable col must not declare server_default, "
            f"AST shows {ast.dump(sd_value)}"
        )
        return
    kind, expected = server_default_spec
    assert sd_value is not None, f"{_TABLE}.{column}: NOT NULL col needs a server_default"
    if kind == "const":
        assert isinstance(sd_value, ast.Constant) and sd_value.value == expected, (
            f"{_TABLE}.{column}: expected server_default={expected!r} (uppercase enum "
            f"label — RB-002 guard), AST shows {ast.dump(sd_value)}"
        )
    elif kind == "call":
        assert isinstance(sd_value, ast.Call), (
            f"{_TABLE}.{column}: expected server_default=sa.{expected}()"
        )
        fn = sd_value.func
        fn_name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", None)
        assert fn_name == expected, (
            f"{_TABLE}.{column}: expected server_default=sa.{expected}(), got sa.{fn_name}()"
        )
    else:  # pragma: no cover - guards against a malformed spec
        pytest.fail(f"unknown server_default spec kind {kind!r}")


@pytest.mark.parametrize(("column", "_nullable", "_sd", "enum_name"), _COHORT)
def test_enum_columns_reference_correct_type(
    column: str, _nullable: bool, _sd: object, enum_name: str | None,
) -> None:
    """``kind`` / ``scan_status`` must use ``sa.Enum(*VALUES, name=<enum_name>)``
    as their column type — pinning the PG enum type name."""
    if enum_name is None:
        return
    upgrade = _upgrade_fn(_migration_tree())
    col_call = _column_call_for(column, upgrade)
    assert len(col_call.args) >= 2, f"{_TABLE}.{column}: sa.Column has no type arg"
    type_arg = col_call.args[1]
    assert (
        isinstance(type_arg, ast.Call)
        and isinstance(type_arg.func, ast.Attribute)
        and type_arg.func.attr == "Enum"
    ), f"{_TABLE}.{column}: type arg must be sa.Enum(...), got {ast.dump(type_arg)}"
    name_kw = None
    for kw in type_arg.keywords:
        if kw.arg == "name" and isinstance(kw.value, ast.Constant):
            name_kw = kw.value.value
    assert name_kw == enum_name, (
        f"{_TABLE}.{column}: sa.Enum name must be {enum_name!r}, AST shows {name_kw!r}"
    )


def test_enum_value_constants_are_uppercase_labels() -> None:
    """RB-002 guard: the module value tuples must equal the uppercase enum NAME
    labels in member order. ``SQLEnum(PyEnum)`` with no ``values_callable``
    persists NAMES, so lowercase ``.value``s here would diverge from what
    ``create_all`` emits and break inserts on PG."""
    values = _module_values(_migration_tree())
    for const_name, expected in _ENUM_VALUE_CONSTANTS.items():
        seq = _string_tuple(values.get(const_name))
        assert seq is not None, (
            f"module constant {const_name} missing or not a string tuple/list"
        )
        assert seq == expected, (
            f"{const_name}: RB-002 guard — expected {expected}, AST shows {seq}"
        )


def test_upgrade_does_not_explicitly_create_enum_types() -> None:
    """``op.add_column`` with a native ``sa.Enum`` auto-emits ``CREATE TYPE`` on
    PG (the iter-42 add_column+enum pattern). An ADDITIONAL explicit
    ``sa.Enum(...).create(...)`` would emit a DUPLICATE ``CREATE TYPE`` and fail
    with 'type already exists'. So upgrade must NOT explicitly create these
    types — pin the auto-create reliance. (Contrast iter-43, which DOES create
    explicitly because it uses the enum in an ``alter_column``, not add_column.)
    """
    upgrade = _upgrade_fn(_migration_tree())
    created = _enum_lifecycle_names(upgrade, "create", require_checkfirst=False)
    assert not ({"file_kind", "file_scan_status"} & created), (
        "upgrade must rely on add_column auto-create, not explicit .create(); "
        f"found explicit create for {sorted(created)}"
    )


def test_enum_types_dropped_in_downgrade_with_checkfirst() -> None:
    """``drop_column`` does NOT auto-drop the PG enum type, so downgrade must
    explicitly ``sa.Enum(name=...).drop(op.get_bind(), checkfirst=True)`` both —
    otherwise the types orphan and a re-upgrade's auto-create hits 'already
    exists' (iter-42 downgrade precedent)."""
    downgrade = _downgrade_fn(_migration_tree())
    dropped = _enum_lifecycle_names(downgrade, "drop", require_checkfirst=True)
    assert {"file_kind", "file_scan_status"} <= dropped, (
        f"downgrade must drop both enum types with checkfirst=True, found {dropped}"
    )


# ---------------------------------------------------------------------------
# Indexes + upgrade/downgrade symmetry.
# ---------------------------------------------------------------------------


def test_indexes_present_in_upgrade() -> None:
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


def test_cohort_size_pinned_at_eight() -> None:
    """Adding/removing a col from this cohort requires updating _COHORT too."""
    upgrade = _upgrade_fn(_migration_tree())
    file_adds = [tn for tn, _ in _add_column_calls(upgrade) if tn == _TABLE]
    assert len(file_adds) == len(_COHORT) == 8


def test_no_create_table_in_upgrade() -> None:
    """iter-47 only adds columns to the existing ``file`` table — no new tables."""
    upgrade = _upgrade_fn(_migration_tree())
    for node in ast.walk(upgrade):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "create_table"
        ):
            pytest.fail("unexpected op.create_table call in iter-47 upgrade")


# ---------------------------------------------------------------------------
# Closed-loop: the lightweight audit must credit the cols and clear the drift.
# ---------------------------------------------------------------------------


def _load_audit():
    audit_path = REPO_ROOT / "scripts" / "audit" / "column_drift_lite.py"
    spec = importlib.util.spec_from_file_location("column_drift_lite", audit_path)
    assert spec is not None and spec.loader is not None
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)
    return audit


def test_audit_credits_iter47_columns() -> None:
    """Closed-loop: after iter-47 ships, ``column_drift_lite`` credits all eight
    cols to the ``file`` table."""
    audit = _load_audit()
    credited = audit.collect_migration_columns().get(_TABLE, set())
    for column, *_ in _COHORT:
        assert column in credited, (
            f"audit doesn't credit {_TABLE}.{column} after iter-47 — "
            f"closed-loop broken (credited={sorted(credited)})"
        )


def test_audit_drift_file_cleared_after_iter47() -> None:
    """Closed-loop: ``file`` must no longer appear in the drift list."""
    audit = _load_audit()
    models = audit.find_versioned_models()
    migration_cols = audit.collect_migration_columns()
    drift = audit.compute_drift(models, migration_cols)
    drift_tables = {info.tablename for info, _missing in drift}
    assert _TABLE not in drift_tables, "file should be cleared by iter-47"
