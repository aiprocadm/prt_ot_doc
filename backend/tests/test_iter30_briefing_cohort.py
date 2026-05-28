"""Pin tests for iter-30 briefing-cohort (flavor (a) drift — 4 absent tables).

iter-30 RB-002t (new release-blocker class — briefing-feature critical drift).
Discovered via ``scripts/audit/version_column_drift.py`` (critical bucket)
and corroborated by ``scripts/audit/check_orm_migration_drift.py``.

Cohort: 4 tables forming the safety-briefing flow (РФ ОТ compliance):
  briefing_templates  → catalog of briefing types
  briefing_journals   → per-site logbooks
  briefing_entries    → per-person briefing events
  briefing_signatures → per-attendee signatures (immutable evidence)

Each pin guards a different invariant:
  - ORM column presence (matches model declarations)
  - FK ondelete semantics matching ORM ``ForeignKey(..., ondelete=...)``
    (these encode the safety-compliance domain rule: delete journal →
    cascade entries; delete template → SET NULL entries (preserve
    evidence the briefing happened))
  - SoftDeleteMixin presence/absence (signatures intentionally immutable)
  - Migration head chain (iter-29 head, NO parallel branch)
  - Cohort scope (exactly 4 create_table calls; not creep-bundled with
    other audit-flagged critical tables)
"""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import inspect

from app.models.base import SoftDeleteMixin
from app.models.models import (
    BriefingEntry,
    BriefingJournal,
    BriefingSignature,
    BriefingTemplate,
)


# (model, tablename, expected_columns).
# Column set verifies both the business cols and the mixin-derived ones
# (id/tenant_id/created_at/updated_at/version from TenantBaseModel,
# deleted_at from SoftDeleteMixin when present).
_COHORT = [
    (
        BriefingTemplate,
        "briefing_templates",
        {
            "id",
            "tenant_id",
            "code",
            "title",
            "briefing_type",
            "status",
            "description",
            "validity_days",
            "deleted_at",
            "created_at",
            "updated_at",
            "version",
        },
    ),
    (
        BriefingJournal,
        "briefing_journals",
        {
            "id",
            "tenant_id",
            "code",
            "title",
            "site_id",
            "department_id",
            "journal_type",
            "status",
            "deleted_at",
            "created_at",
            "updated_at",
            "version",
        },
    ),
    (
        BriefingEntry,
        "briefing_entries",
        {
            "id",
            "tenant_id",
            "briefing_journal_id",
            "briefing_template_id",
            "person_id",
            "instructor_user_id",
            "site_id",
            "department_id",
            "workplace_id",
            "briefing_type",
            "briefing_date",
            "valid_until",
            "reason",
            "status",
            "notes",
            "deleted_at",
            "created_at",
            "updated_at",
            "version",
        },
    ),
    (
        BriefingSignature,
        "briefing_signatures",
        {
            "id",
            "tenant_id",
            "briefing_entry_id",
            "signer_type",
            "signer_user_id",
            "signer_person_id",
            "signature_mode",
            "signed_at",
            "signature_payload",
            "created_at",
            "updated_at",
            "version",
            # NB: deliberately NO deleted_at — see signatures-immutable test.
        },
    ),
]


@pytest.mark.parametrize(("model", "tablename", "expected_columns"), _COHORT)
def test_briefing_cohort_columns_present(model, tablename, expected_columns) -> None:
    actual_columns = set(inspect(model).columns.keys())
    missing = expected_columns - actual_columns
    extra = actual_columns - expected_columns
    assert not missing, f"{tablename} missing expected columns: {missing}"
    assert not extra, (
        f"{tablename} has unexpected columns: {extra}. "
        "If you intentionally added a new column, update both the model "
        "AND this test's expected_columns set in the same PR."
    )


# ---- FK ondelete semantics --------------------------------------------------


# (model, column_name, expected_target_table, expected_ondelete, rationale).
# Each row encodes a safety-compliance domain rule. Changing these silently
# means the compliance semantics have shifted — should be a deliberate PR.
_FK_CONTRACT = [
    (
        BriefingJournal,
        "site_id",
        "site",
        "SET NULL",
        "deleting a site (reorg) must not destroy briefing journals",
    ),
    (
        BriefingJournal,
        "department_id",
        "department",
        "SET NULL",
        "deleting a department (reorg) must not destroy briefing journals",
    ),
    (
        BriefingEntry,
        "briefing_journal_id",
        "briefing_journals",
        "CASCADE",
        "deleting a journal is a deliberate operator action — entries cease",
    ),
    (
        BriefingEntry,
        "briefing_template_id",
        "briefing_templates",
        "SET NULL",
        "deleting a template must NOT destroy evidence that the briefing happened",
    ),
    (
        BriefingEntry,
        "person_id",
        "person",
        "SET NULL",
        "deleting a person must not destroy compliance history",
    ),
    (
        BriefingEntry,
        "site_id",
        "site",
        "SET NULL",
        "site reorg must not destroy briefing entries",
    ),
    (
        BriefingEntry,
        "department_id",
        "department",
        "SET NULL",
        "department reorg must not destroy briefing entries",
    ),
    (
        BriefingEntry,
        "workplace_id",
        "workplace",
        "SET NULL",
        "workplace reorg must not destroy briefing entries",
    ),
    (
        BriefingSignature,
        "briefing_entry_id",
        "briefing_entries",
        "CASCADE",
        "a signature has no meaning without its parent entry",
    ),
    (
        BriefingSignature,
        "signer_person_id",
        "person",
        "SET NULL",
        "deleting a person must not destroy signature compliance evidence",
    ),
]


@pytest.mark.parametrize(
    ("model", "column_name", "expected_target", "expected_ondelete", "rationale"),
    _FK_CONTRACT,
)
def test_briefing_fk_ondelete_semantics(
    model, column_name, expected_target, expected_ondelete, rationale
) -> None:
    column = inspect(model).columns[column_name]
    foreign_keys = list(column.foreign_keys)
    assert len(foreign_keys) == 1, (
        f"{model.__name__}.{column_name} expected 1 FK; got {len(foreign_keys)}"
    )
    fk = foreign_keys[0]
    assert fk.column.table.name == expected_target, (
        f"{model.__name__}.{column_name} FK target drift: "
        f"got {fk.column.table.name!r}, expected {expected_target!r}"
    )
    assert fk.ondelete == expected_ondelete, (
        f"{model.__name__}.{column_name} ondelete drift: "
        f"got {fk.ondelete!r}, expected {expected_ondelete!r}. "
        f"Rationale: {rationale}"
    )


# ---- SoftDeleteMixin contract ----------------------------------------------


@pytest.mark.parametrize(
    ("model", "expected_soft_delete"),
    [
        (BriefingTemplate, True),
        (BriefingJournal, True),
        (BriefingEntry, True),
        (BriefingSignature, False),
    ],
)
def test_briefing_soft_delete_contract(model, expected_soft_delete) -> None:
    inherits = issubclass(model, SoftDeleteMixin)
    has_column = "deleted_at" in inspect(model).columns
    assert inherits is expected_soft_delete, (
        f"{model.__name__} SoftDeleteMixin inheritance drift: "
        f"got {inherits}, expected {expected_soft_delete}"
    )
    assert has_column is expected_soft_delete, (
        f"{model.__name__} deleted_at column drift: got {has_column}, "
        f"expected {expected_soft_delete}. "
        "BriefingSignature must remain immutable — it is compliance "
        "evidence; only CASCADE from parent entry can remove it."
    )


# ---- Unique constraints ----------------------------------------------------


@pytest.mark.parametrize(
    ("model", "constraint_name", "expected_columns"),
    [
        (BriefingTemplate, "uq_briefing_templates_code", ("tenant_id", "code")),
        (BriefingJournal, "uq_briefing_journals_code", ("tenant_id", "code")),
    ],
)
def test_briefing_unique_constraints(
    model, constraint_name, expected_columns
) -> None:
    constraints = {
        c.name: tuple(col.name for col in c.columns)
        for c in model.__table__.constraints
        if hasattr(c, "columns") and c.name == constraint_name
    }
    assert constraint_name in constraints, (
        f"{model.__name__} missing constraint {constraint_name!r}. "
        "Tenant-scoped code uniqueness is a business invariant — "
        "duplicate codes would corrupt downstream lookup logic."
    )
    assert constraints[constraint_name] == expected_columns, (
        f"{constraint_name} column drift: "
        f"got {constraints[constraint_name]}, expected {expected_columns}"
    )


# ---- Migration-side guards --------------------------------------------------


def _load_iter30_migration():
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "migrations"
        / "versions"
        / "20260528_iter30_briefing_cohort.py"
    )
    assert migration_path.exists(), (
        f"iter-30 migration file missing at {migration_path}"
    )
    spec = importlib.util.spec_from_file_location("iter30_migration", migration_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_iter30_migration_chains_to_iter29_head() -> None:
    module = _load_iter30_migration()
    assert module.revision == "20260528_iter30_briefing_cohort"
    # iter-29 (version retrofit) was the most recent migration on the
    # iter-30 base branch. iter-27/28 were app-code only (no migration),
    # so iter-29 stays the head.
    assert module.down_revision == "20260528_iter29_version_retrofit", (
        f"iter-30 down_revision drift: got {module.down_revision!r}; "
        "expected '20260528_iter29_version_retrofit'. See [[alembic-heads-lesson]] — "
        "filename ≠ revision id; always verify true head with grep before "
        "setting down_revision."
    )


def test_iter30_migration_creates_exactly_4_briefing_tables() -> None:
    # Scope guard. If a future edit bundles another audit-flagged
    # critical table here, this test fails — forces splitting into
    # its own iter (which preserves the cohort-discipline pattern).
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "migrations"
        / "versions"
        / "20260528_iter30_briefing_cohort.py"
    )
    tree = ast.parse(migration_path.read_text(encoding="utf-8"))
    upgrade_fn = next(
        (n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "upgrade"),
        None,
    )
    assert upgrade_fn is not None, "iter-30 migration missing upgrade()"
    created_tables: list[str] = []
    for node in ast.walk(upgrade_fn):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if (
            isinstance(func, ast.Attribute)
            and func.attr == "create_table"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            created_tables.append(node.args[0].value)
    expected = [
        "briefing_templates",
        "briefing_journals",
        "briefing_entries",
        "briefing_signatures",
    ]
    assert created_tables == expected, (
        f"iter-30 must create exactly 4 briefing tables in FK-dependency "
        f"order; got {created_tables}, expected {expected}. "
        "Order matters: briefing_entries FK-depends on briefing_journals "
        "+ briefing_templates being present; briefing_signatures FK-depends "
        "on briefing_entries. Wrong order = create-time FK constraint violation."
    )


def test_iter30_version_columns_have_server_default() -> None:
    # ``version`` is from VersionedMixin. NEW tables theoretically don't
    # NEED server_default (no rows to backfill), but iter-30 keeps it for
    # consistency with iter-29 / next57 precedent AND because raw-SQL
    # INSERTs (test fixtures, ops repair scripts) that bypass ORM's
    # python-side ``default=1`` would otherwise hit NOT NULL violation.
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "migrations"
        / "versions"
        / "20260528_iter30_briefing_cohort.py"
    )
    tree = ast.parse(migration_path.read_text(encoding="utf-8"))
    upgrade_fn = next(
        (n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "upgrade"),
        None,
    )
    assert upgrade_fn is not None
    version_columns_with_default = 0
    for node in ast.walk(upgrade_fn):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "Column"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and node.args[0].value == "version"
        ):
            continue
        # Look for server_default="1" keyword.
        for kw in node.keywords:
            if (
                kw.arg == "server_default"
                and isinstance(kw.value, ast.Constant)
                and kw.value.value == "1"
            ):
                version_columns_with_default += 1
                break
    assert version_columns_with_default == 4, (
        f"All 4 briefing tables must declare version with server_default='1'; "
        f"got {version_columns_with_default}. Raw-SQL inserts that bypass "
        "ORM python-side default=1 will violate NOT NULL otherwise."
    )


def test_iter30_downgrade_reverses_upgrade_table_order() -> None:
    # FK-dependency order on creation is templates → journals → entries
    # → signatures. Downgrade must drop in the reverse order or
    # CASCADE-less drops will fail at the DB level when child rows
    # still reference the parent.
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "migrations"
        / "versions"
        / "20260528_iter30_briefing_cohort.py"
    )
    tree = ast.parse(migration_path.read_text(encoding="utf-8"))
    downgrade_fn = next(
        (
            n
            for n in tree.body
            if isinstance(n, ast.FunctionDef) and n.name == "downgrade"
        ),
        None,
    )
    assert downgrade_fn is not None
    dropped_tables: list[str] = []
    for node in ast.walk(downgrade_fn):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "drop_table"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            dropped_tables.append(node.args[0].value)
    expected = [
        "briefing_signatures",
        "briefing_entries",
        "briefing_journals",
        "briefing_templates",
    ]
    assert dropped_tables == expected, (
        f"Downgrade must reverse FK-dependency order; "
        f"got {dropped_tables}, expected {expected}"
    )
