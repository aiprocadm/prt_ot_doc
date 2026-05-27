"""iter-25: add training_course / training_plan / training_session tables missing from migrations.

Revision ID: 20260527_iter25_training_family
Revises: 20260527_iter24_journal_ppeitem
Create Date: 2026-05-27

Cohort fix for three ``critical`` ORM↔migration drifts surfaced by
``scripts/audit/check_orm_migration_drift.py`` (see Session 71/72 handoffs).
After iter-24 closed the audit_export_job/journal/ppeitem triplet, the
audit ``--summary`` still flagged 6 critical tables; this PR closes the
training family (3 of those 6). Remaining 3 after this PR:
``incident_log``, ``incident_person``, ``inspection_result`` — deferred
because the ``incident`` parent table itself has business drift (7 cols
missing including ``status: Enum``), which requires its own enum-design
pass before child tables can be safely created.

Root cause (all three):
  - Models declared in ``backend/app/models/models.py:840-925``
    (``TrainingCourse``, ``TrainingPlan``, ``TrainingSession``).
  - All three referenced by application code: ``backend/app/modules/training/``
    services + ``backend/app/api/routes/training.py`` endpoints + admin
    bootstrap flows.
  - Zero ``op.create_table('training_course'|'training_plan'|'training_session')``
    matches across ``backend/app/migrations/versions/*.py``.
  - SQLite tests pass (``Base.metadata.create_all()`` from model side);
    Postgres crashes on the first ORM query against any of these tables.

Companion enum type (NEW — verified absent from migration tree before
this PR via grep):
  - ``trainingsessionstatus``: scheduled / in_progress / completed / failed
    (values are the lowercase ``str, enum.Enum`` value strings from
    ``models.py:TrainingSessionStatus``).

Note on ``TrainingStatus`` (the simpler legacy ``Training`` class at
``models.py:823``): NOT in scope here. ``Training`` table itself is also
drift (also missing ``create_table``), but it is a separate legacy entity
and may itself be deprecated in favour of ``TrainingSession``. Defer to
a follow-up iter.

Antipattern guards:
  - A1 (enum double-create): ``trainingsessionstatus`` name is fresh —
    verified via ``grep -rn name=\"trainingsessionstatus\" migrations/`` →
    zero matches. Safe to let SQLAlchemy ``sa.Enum(..., name=X)`` auto-create.
  - A3 (drop-recreate enum on dependent column): not applicable here —
    new enum bound to new column in the same migration.

Intra-migration FK order (important for ``op.create_table`` succession):
  1. ``training_course`` — no intra-cohort FKs.
  2. ``training_plan`` — FK to ``training_course.id`` (CASCADE).
  3. ``training_session`` — FK to ``training_course.id`` (CASCADE) +
     ``training_plan.id`` (SET NULL).

Cohort rationale (per [[rb002-enum-migration-cohort]]):
  - Same root cause (model-without-migration anti-pattern).
  - Same discovery (one audit script run).
  - Same domain: tightly-coupled training catalog hierarchy
    (course → plan → session). Landing one without the others would
    fail closed-loop validation (audit script would still flag two).
  - Strong intra-cohort coupling (FKs across all three) — bundling
    enforces atomic apply.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260527_iter25_training_family"
down_revision: str | Sequence[str] | None = "20260527_iter24_journal_ppeitem"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


TRAINING_SESSION_STATUS_VALUES = (
    "scheduled",
    "in_progress",
    "completed",
    "failed",
)


def upgrade() -> None:
    # --- training_course ----------------------------------------------------
    op.create_table(
        "training_course",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("duration_hours", sa.Integer(), nullable=True),
        sa.Column("valid_period_days", sa.Integer(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenant.id"], name="fk_training_course_tenant"
        ),
        sa.UniqueConstraint("tenant_id", "title", name="uq_training_course_title"),
    )
    op.create_index(
        "ix_training_course_tenant_id", "training_course", ["tenant_id"], unique=False
    )
    op.create_index(
        "ix_training_course_code",
        "training_course",
        ["tenant_id", "code"],
        unique=False,
    )

    # --- training_plan ------------------------------------------------------
    op.create_table(
        "training_plan",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("company_id", sa.String(length=36), nullable=False),
        sa.Column("position_id", sa.String(length=36), nullable=True),
        sa.Column("person_id", sa.String(length=36), nullable=True),
        sa.Column("course_id", sa.String(length=36), nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("is_mandatory", sa.Boolean(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenant.id"], name="fk_training_plan_tenant"
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["company.id"],
            name="fk_training_plan_company",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["position_id"],
            ["position.id"],
            name="fk_training_plan_position",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["person_id"],
            ["person.id"],
            name="fk_training_plan_person",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["course_id"],
            ["training_course.id"],
            name="fk_training_plan_course",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "course_id",
            "company_id",
            "position_id",
            "person_id",
            name="uq_training_plan_target",
        ),
    )
    op.create_index(
        "ix_training_plan_tenant_id", "training_plan", ["tenant_id"], unique=False
    )
    op.create_index(
        "ix_training_plan_company_id", "training_plan", ["company_id"], unique=False
    )
    op.create_index(
        "ix_training_plan_position_id", "training_plan", ["position_id"], unique=False
    )
    op.create_index(
        "ix_training_plan_person_id", "training_plan", ["person_id"], unique=False
    )
    op.create_index(
        "ix_training_plan_course_id", "training_plan", ["course_id"], unique=False
    )

    # --- training_session ---------------------------------------------------
    op.create_table(
        "training_session",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("person_id", sa.String(length=36), nullable=False),
        sa.Column("course_id", sa.String(length=36), nullable=False),
        sa.Column("plan_id", sa.String(length=36), nullable=True),
        sa.Column(
            "status",
            sa.Enum(*TRAINING_SESSION_STATUS_VALUES, name="trainingsessionstatus"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenant.id"], name="fk_training_session_tenant"
        ),
        sa.ForeignKeyConstraint(
            ["person_id"],
            ["person.id"],
            name="fk_training_session_person",
        ),
        sa.ForeignKeyConstraint(
            ["course_id"],
            ["training_course.id"],
            name="fk_training_session_course",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["plan_id"],
            ["training_plan.id"],
            name="fk_training_session_plan",
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_training_session_tenant_id",
        "training_session",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        "ix_training_session_person_id",
        "training_session",
        ["person_id"],
        unique=False,
    )
    op.create_index(
        "ix_training_session_course_id",
        "training_session",
        ["course_id"],
        unique=False,
    )
    op.create_index(
        "ix_training_session_plan_id",
        "training_session",
        ["plan_id"],
        unique=False,
    )
    op.create_index(
        "ix_training_session_status",
        "training_session",
        ["tenant_id", "status"],
        unique=False,
    )


def downgrade() -> None:
    # Drop in reverse FK-order: session → plan → course.
    op.drop_index("ix_training_session_status", table_name="training_session")
    op.drop_index("ix_training_session_plan_id", table_name="training_session")
    op.drop_index("ix_training_session_course_id", table_name="training_session")
    op.drop_index("ix_training_session_person_id", table_name="training_session")
    op.drop_index("ix_training_session_tenant_id", table_name="training_session")
    op.drop_table("training_session")

    op.drop_index("ix_training_plan_course_id", table_name="training_plan")
    op.drop_index("ix_training_plan_person_id", table_name="training_plan")
    op.drop_index("ix_training_plan_position_id", table_name="training_plan")
    op.drop_index("ix_training_plan_company_id", table_name="training_plan")
    op.drop_index("ix_training_plan_tenant_id", table_name="training_plan")
    op.drop_table("training_plan")

    op.drop_index("ix_training_course_code", table_name="training_course")
    op.drop_index("ix_training_course_tenant_id", table_name="training_course")
    op.drop_table("training_course")

    # Drop enum type last (Postgres-only — SQLite uses inline CHECK constraints
    # which auto-clean with the column drop).
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        sa.Enum(name="trainingsessionstatus").drop(bind, checkfirst=True)
