"""Pin tests for ``TrainingCourse`` (``training_course`` table) schema parity.

iter-25 RB-002o (NEW release-blocker class — same anti-pattern as iter-23/24:
model-without-migration drift). Discovered by
``scripts/audit/check_orm_migration_drift.py`` (Session 71+72 ``--summary``
classified ``training_course`` as ``critical``).

Migration ``20260527_iter25_training_family`` creates the table with the
catalog-side training nomenclature. This file pins the model-side contract
so future regressions — dropping the unique constraint on (tenant_id, title),
losing the soft-delete column, renaming an index — trip backend-tests
before reaching Postgres.

Cohort partner tables: ``training_plan`` (FK to course) + ``training_session``
(FK to course + plan). See sibling pin-test files.
"""

from __future__ import annotations

from sqlalchemy import inspect

from app.models.models import TrainingCourse


def test_training_course_has_required_columns() -> None:
    columns = inspect(TrainingCourse).columns
    required = {
        "id",
        "tenant_id",
        "title",
        "code",
        "description",
        "duration_hours",
        "valid_period_days",
        "metadata_json",
        "deleted_at",
        "created_at",
        "updated_at",
        "version",
    }
    assert required.issubset(columns.keys()), (
        f"training_course missing columns: {required - set(columns.keys())}"
    )


def test_training_course_unique_title_per_tenant() -> None:
    # Catalog uniqueness: same tenant cannot have two courses with the same
    # title — duplicate names would break human-readable course pickers.
    unique_names = {uc.name for uc in TrainingCourse.__table__.constraints if hasattr(uc, "columns") and uc.name and uc.name.startswith("uq_")}
    assert "uq_training_course_title" in unique_names, (
        "uq_training_course_title (tenant_id, title) is required; without it "
        "tenants can accumulate duplicate course nomenclature entries"
    )


def test_training_course_code_lookup_index() -> None:
    index_names = {idx.name for idx in TrainingCourse.__table__.indexes}
    assert "ix_training_course_code" in index_names, (
        "ix_training_course_code on (tenant_id, code) is required for "
        "tenant-scoped code lookups (catalog import / external_registry sync)"
    )


def test_training_course_soft_delete_column_present() -> None:
    # SoftDeleteMixin contract: tombstone instead of hard delete. Catalog
    # entries are referenced by historical TrainingSession rows; hard-delete
    # would orphan history.
    assert "deleted_at" in inspect(TrainingCourse).columns, (
        "TrainingCourse must use SoftDeleteMixin — historical training "
        "sessions reference course rows and cannot tolerate hard delete"
    )
