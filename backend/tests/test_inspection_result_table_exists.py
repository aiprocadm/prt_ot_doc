"""Pin tests for ``InspectionResult`` (``inspection_result`` table) schema parity.

iter-26 RB-002r (NEW release-blocker class — model-without-migration drift).
Discovered by ``scripts/audit/check_orm_migration_drift.py`` (``critical``).

Standalone (no cohort) — the other two remaining critical drifts
(``incident_log``, ``incident_person``) are deferred until parent
``incident`` business-drift + enum-design pass.

Migration ``20260527_iter26_inspection_result`` creates the table with
FKs to ``regulatory_inspection`` (CASCADE — matches ORM parent's
``cascade="all, delete-orphan"``) and ``file`` (SET NULL — file deletion
should not destroy the result record).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from sqlalchemy import inspect

from app.models.models import InspectionResult


def test_inspection_result_has_required_columns() -> None:
    columns = inspect(InspectionResult).columns
    required = {
        "id",
        "tenant_id",
        "inspection_id",
        "title",
        "outcome",
        "notes",
        "issued_at",
        "file_id",
        "deleted_at",
        "created_at",
        "updated_at",
        "version",
    }
    assert required.issubset(columns.keys()), (
        f"inspection_result missing columns: {required - set(columns.keys())}"
    )


def test_inspection_result_inspection_fk_cascades() -> None:
    column = inspect(InspectionResult).columns["inspection_id"]
    foreign_keys = list(column.foreign_keys)
    assert len(foreign_keys) == 1
    fk = foreign_keys[0]
    assert fk.column.table.name == "regulatory_inspection"
    assert fk.ondelete == "CASCADE", (
        "ondelete must be CASCADE — matches the ORM parent's "
        "cascade='all, delete-orphan' on Inspection.results; without "
        "CASCADE the orphan-delete fails at DB level"
    )


def test_inspection_result_file_fk_sets_null() -> None:
    column = inspect(InspectionResult).columns["file_id"]
    foreign_keys = list(column.foreign_keys)
    assert len(foreign_keys) == 1
    fk = foreign_keys[0]
    assert fk.column.table.name == "file"
    assert fk.ondelete == "SET NULL", (
        "ondelete must be SET NULL — file is a side-attachment; if the "
        "underlying file blob is removed, the inspection record (a "
        "regulatory artifact) must survive with detached file_id"
    )


def test_inspection_result_composite_index_for_tenant_inspection_lookup() -> None:
    index_names = {idx.name for idx in InspectionResult.__table__.indexes}
    assert "ix_inspection_result_inspection" in index_names, (
        "ix_inspection_result_inspection on (tenant_id, inspection_id) is "
        "the hot-path index for the parent-side relationship lookup "
        "(Inspection.results selectin-load)"
    )


def test_inspection_result_issued_at_lookup_index() -> None:
    # Date-range queries for compliance reports filter by issued_at;
    # without the index, large tenants trigger seq-scan.
    index_names = {idx.name for idx in InspectionResult.__table__.indexes}
    assert "ix_inspection_result_issued_at" in index_names, (
        "ix_inspection_result_issued_at is required for date-range "
        "compliance reporting (issued_at BETWEEN ... AND ...)"
    )


def _load_iter26_migration():
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "migrations"
        / "versions"
        / "20260527_iter26_inspection_result.py"
    )
    assert migration_path.exists(), (
        f"iter-26 migration file missing at {migration_path}"
    )
    spec = importlib.util.spec_from_file_location("iter26_migration", migration_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_iter26_migration_chains_to_iter25_head() -> None:
    module = _load_iter26_migration()
    assert module.revision == "20260527_iter26_inspection_result"
    # iter-26 stacks on iter-25 (PR #594) — chaining to an older revision
    # would create a parallel branch and break ``alembic upgrade head``.
    # See [[alembic-heads-lesson]] (iter-21 PR #589 first attempt cost).
    assert module.down_revision == "20260527_iter25_training_family", (
        f"iter-26 down_revision drift: got {module.down_revision!r}; "
        "expected '20260527_iter25_training_family' (iter-25's head)"
    )


def test_iter26_migration_creates_inspection_result_only() -> None:
    # Cohort discipline: this iter is intentionally standalone.
    # Anything else added here is scope creep.
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "migrations"
        / "versions"
        / "20260527_iter26_inspection_result.py"
    )
    src = migration_path.read_text(encoding="utf-8")
    assert 'op.create_table(\n        "inspection_result"' in src, (
        "iter-26 must create the inspection_result table"
    )
    # Guard: no other table create — iter-26 is standalone.
    create_table_count = src.count("op.create_table(")
    assert create_table_count == 1, (
        f"iter-26 must create exactly 1 table; got {create_table_count}. "
        "If you bundled another table, split it into a separate iter."
    )
