"""Pin tests for ``TrainingPlan`` (``training_plan`` table) schema parity.

iter-25 RB-002p (NEW release-blocker class — model-without-migration drift).
Discovered by ``scripts/audit/check_orm_migration_drift.py`` (``critical``).

Migration ``20260527_iter25_training_family`` creates the table with FKs
to company (CASCADE), position (SET NULL), person (SET NULL), and
training_course (CASCADE). This file pins the model-side FK ondelete
behavior so future migrations cannot silently degrade cascade semantics
(e.g. switching company→SET NULL would orphan compliance plans).
"""

from __future__ import annotations

from sqlalchemy import inspect

from app.models.models import TrainingPlan


def test_training_plan_has_required_columns() -> None:
    columns = inspect(TrainingPlan).columns
    required = {
        "id",
        "tenant_id",
        "company_id",
        "position_id",
        "person_id",
        "course_id",
        "assigned_at",
        "due_date",
        "is_mandatory",
        "deleted_at",
        "created_at",
        "updated_at",
        "version",
    }
    assert required.issubset(
        columns.keys()
    ), f"training_plan missing columns: {required - set(columns.keys())}"


def test_training_plan_company_fk_cascades_on_delete() -> None:
    column = inspect(TrainingPlan).columns["company_id"]
    foreign_keys = list(column.foreign_keys)
    assert len(foreign_keys) == 1
    fk = foreign_keys[0]
    assert fk.column.table.name == "company"
    assert fk.ondelete == "CASCADE", (
        "ondelete must be CASCADE — when a company is removed, its training "
        "plans should disappear with it (not orphan with NULL company_id)"
    )


def test_training_plan_course_fk_cascades_on_delete() -> None:
    column = inspect(TrainingPlan).columns["course_id"]
    foreign_keys = list(column.foreign_keys)
    assert len(foreign_keys) == 1
    fk = foreign_keys[0]
    assert fk.column.table.name == "training_course"
    assert fk.ondelete == "CASCADE", (
        "ondelete must be CASCADE — a plan without its course is meaningless; "
        "course deletion (soft or hard) should propagate to plans"
    )


def test_training_plan_position_and_person_fks_set_null() -> None:
    # position and person are nullable targets — a plan can outlive both
    # (e.g. position renamed, person left the company). SET NULL preserves
    # the plan with detached targets.
    for col_name, expected_table in (("position_id", "position"), ("person_id", "person")):
        column = inspect(TrainingPlan).columns[col_name]
        foreign_keys = list(column.foreign_keys)
        assert len(foreign_keys) == 1, f"{col_name} must have one FK"
        fk = foreign_keys[0]
        assert fk.column.table.name == expected_table
        assert fk.ondelete == "SET NULL", (
            f"{col_name} ondelete must be SET NULL — losing the {expected_table} "
            f"should not destroy the historical training assignment"
        )


def test_training_plan_target_uniqueness_5col() -> None:
    # The 5-col unique constraint (tenant_id, course_id, company_id,
    # position_id, person_id) prevents duplicate assignments — without it,
    # repeated POST /training-plans calls would create silent duplicates.
    unique_constraint_names = {
        c.name
        for c in TrainingPlan.__table__.constraints
        if hasattr(c, "columns") and c.name and c.name.startswith("uq_")
    }
    assert "uq_training_plan_target" in unique_constraint_names, (
        "uq_training_plan_target (5 cols) is required to prevent duplicate "
        "course assignments per (company, position, person) tuple"
    )
