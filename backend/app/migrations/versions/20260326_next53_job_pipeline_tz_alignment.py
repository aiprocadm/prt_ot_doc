"""next53 job pipeline orchestration tz alignment

Revision ID: 20260326_next53
Revises: 20260325_next52
Create Date: 2026-03-26 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "20260326_next53"
down_revision = "20260325_next52"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "document_jobs", sa.Column("queued_at", sa.DateTime(timezone=True), nullable=True)
    )

    op.add_column("document_job_steps", sa.Column("seq", sa.Integer(), nullable=True))
    op.add_column(
        "document_job_steps",
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("document_job_steps", sa.Column("logs_ref", sa.String(length=512), nullable=True))

    op.execute(
        'UPDATE document_job_steps SET seq = COALESCE(step_order, "order") WHERE seq IS NULL'
    )
    op.execute("UPDATE document_job_steps SET attempt = COALESCE(attempts, 0) WHERE attempt = 0")

    op.create_index("ix_document_job_steps_job_seq", "document_job_steps", ["job_id", "seq"])
    # iter-15c: `ix_document_job_steps_job_status` is also created by
    # 20260314_next40_pipeline_locks_and_indexes:36 (sibling branch in the
    # DAG). At alembic upgrade-head time the next40 branch lands first and
    # the unconditional op.create_index here fails with DuplicateTableError.
    # Use CREATE INDEX IF NOT EXISTS via raw SQL so this revision is
    # idempotent regardless of which branch wins the race. Postgres ≥9.5
    # supports IF NOT EXISTS on CREATE INDEX; SQLite 3.8+ also supports it.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_document_job_steps_job_status "
        "ON document_job_steps (job_id, status)"
    )

    op.add_column(
        "pipeline_profiles", sa.Column("concurrency_limit_per_tenant", sa.Integer(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("pipeline_profiles", "concurrency_limit_per_tenant")

    # iter-15c mirror: ix_document_job_steps_job_status is co-created (IF NOT
    # EXISTS) by both this revision and 20260314_next40 (sibling DAG branch).
    # The branch that downgrades second would hit "index does not exist", so
    # drop it idempotently to match the idempotent create above.
    op.execute("DROP INDEX IF EXISTS ix_document_job_steps_job_status")
    op.drop_index("ix_document_job_steps_job_seq", table_name="document_job_steps")

    op.drop_column("document_job_steps", "logs_ref")
    op.drop_column("document_job_steps", "attempt")
    op.drop_column("document_job_steps", "seq")

    op.drop_column("document_jobs", "queued_at")
