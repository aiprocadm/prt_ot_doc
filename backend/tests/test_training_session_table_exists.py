"""Pin tests for ``TrainingSession`` (``training_session`` table) schema parity.

iter-25 RB-002q (NEW release-blocker class — model-without-migration drift).
Discovered by ``scripts/audit/check_orm_migration_drift.py`` (``critical``).

Migration ``20260527_iter25_training_family`` creates the table with FKs
to person, training_course (CASCADE), training_plan (SET NULL), and the
new ``trainingsessionstatus`` PG enum. This file also pins the iter-25
migration chain to iter-24 head (per [[alembic-heads-lesson]]) and the
all-three-tables-in-one-migration scope guard (cohort discipline).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from sqlalchemy import inspect

from app.models.models import TrainingSession, TrainingSessionStatus


def test_training_session_has_required_columns() -> None:
    columns = inspect(TrainingSession).columns
    required = {
        "id",
        "tenant_id",
        "person_id",
        "course_id",
        "plan_id",
        "status",
        "started_at",
        "completed_at",
        "score",
        "notes",
        "created_at",
        "updated_at",
        "version",
    }
    assert required.issubset(
        columns.keys()
    ), f"training_session missing columns: {required - set(columns.keys())}"
    # Note: training_session deliberately does NOT use SoftDeleteMixin —
    # sessions are immutable historical events, not catalog entries.
    assert "deleted_at" not in columns, (
        "training_session is event-historical and must not be soft-deletable; "
        "if you need to retract a session, add a 'voided' boolean instead"
    )


def test_training_session_status_uses_enum_class() -> None:
    column = inspect(TrainingSession).columns["status"]
    # SQLAlchemy stores the enum class on column.type for sa.Enum(PyEnum).
    assert column.type.enum_class is TrainingSessionStatus, (
        "training_session.status must be Enum(TrainingSessionStatus) — a "
        "String column would lose Postgres-side validation of allowed values"
    )
    expected_values = {"scheduled", "in_progress", "completed", "failed"}
    actual_values = {member.value for member in TrainingSessionStatus}
    assert expected_values == actual_values, (
        f"TrainingSessionStatus value drift: {expected_values ^ actual_values}. "
        "If you add a value, also extend the PG enum via ALTER TYPE in a "
        "separate revision (see [[rb002-enum-migration-cohort]] iter-19)."
    )


def test_training_session_course_fk_cascades_on_delete() -> None:
    column = inspect(TrainingSession).columns["course_id"]
    foreign_keys = list(column.foreign_keys)
    assert len(foreign_keys) == 1
    fk = foreign_keys[0]
    assert fk.column.table.name == "training_course"
    assert fk.ondelete == "CASCADE", (
        "ondelete must be CASCADE — sessions without their course are "
        "meaningless and should be removed when the course is removed"
    )


def test_training_session_plan_fk_sets_null() -> None:
    column = inspect(TrainingSession).columns["plan_id"]
    foreign_keys = list(column.foreign_keys)
    assert len(foreign_keys) == 1
    fk = foreign_keys[0]
    assert fk.column.table.name == "training_plan"
    assert fk.ondelete == "SET NULL", (
        "ondelete must be SET NULL — plan deletion should not erase the "
        "session record (historical evidence preserved with detached plan_id)"
    )


def test_training_session_status_lookup_index() -> None:
    index_names = {idx.name for idx in TrainingSession.__table__.indexes}
    assert "ix_training_session_status" in index_names, (
        "ix_training_session_status on (tenant_id, status) is required for "
        "tenant-scoped status filtering (e.g. dashboard 'in_progress' counts)"
    )


def _load_iter25_migration():
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "migrations"
        / "versions"
        / "20260527_iter25_training_family.py"
    )
    assert migration_path.exists(), f"iter-25 migration file missing at {migration_path}"
    spec = importlib.util.spec_from_file_location("iter25_migration", migration_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_iter25_migration_chains_to_iter24_head() -> None:
    module = _load_iter25_migration()
    assert module.revision == "20260527_iter25_training_family"
    # iter-25 must chain to iter-24 (current head as of branch creation) —
    # chaining to an older revision would create a parallel branch and break
    # ``alembic upgrade head`` with "Multiple head revisions" (the lesson
    # from iter-21 PR #589 first attempt — see [[alembic-heads-lesson]]).
    assert module.down_revision == "20260527_iter24_journal_ppeitem", (
        f"iter-25 down_revision drift: got {module.down_revision!r}; "
        "expected '20260527_iter24_journal_ppeitem' (true head verified by "
        "grep -rln 'down_revision.*20260527_iter24_journal_ppeitem' before commit)"
    )


def test_iter25_migration_creates_all_three_cohort_tables() -> None:
    # Cohort discipline: this migration must create exactly the three tables
    # it announces in its docstring. Adding more or fewer is a scope error.
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "migrations"
        / "versions"
        / "20260527_iter25_training_family.py"
    )
    src = migration_path.read_text(encoding="utf-8")
    for table_name in ("training_course", "training_plan", "training_session"):
        assert (
            f'op.create_table(\n        "{table_name}"' in src
        ), f"iter-25 must create the {table_name} table"


def test_iter25_migration_declares_trainingsessionstatus_enum() -> None:
    # The enum is fresh in the migration tree (A1 antipattern guard
    # confirmed pre-commit). The migration source must spell the enum
    # name so audit tools can pick it up by string search.
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "migrations"
        / "versions"
        / "20260527_iter25_training_family.py"
    )
    src = migration_path.read_text(encoding="utf-8")
    assert 'name="trainingsessionstatus"' in src, (
        "iter-25 must declare the trainingsessionstatus PG enum by name; "
        "if you rename it, also update [[rb002-enum-migration-cohort]] memory"
    )
