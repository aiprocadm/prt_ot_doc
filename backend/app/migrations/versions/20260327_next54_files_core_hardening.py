"""next54 files core hardening

Revision ID: 20260327_next54
Revises: 20260326_next53_job_pipeline_tz_alignment
Create Date: 2026-03-27 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "20260327_next54"
down_revision = "20260326_next53"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("files", "bucket", existing_type=sa.String(length=255), server_default="ptd")
    op.execute("UPDATE files SET bucket = 'ptd' WHERE bucket IS NULL OR bucket = 'main'")

    with op.batch_alter_table("files") as batch_op:
        batch_op.create_index("ix_files_tenant_object_key", ["tenant_id", "object_key"], unique=True)

    with op.batch_alter_table("file_download_logs") as batch_op:
        batch_op.add_column(sa.Column("action", sa.String(length=32), nullable=True, server_default="presigned_url_issued"))

    op.execute(
        "UPDATE file_download_logs SET action = 'presigned_url_issued' WHERE action IS NULL"
    )
    with op.batch_alter_table("file_download_logs") as batch_op:
        batch_op.alter_column("action", existing_type=sa.String(length=32), nullable=False)
        batch_op.create_index("ix_file_download_logs_tenant_created_at", ["tenant_id", "created_at"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("file_download_logs") as batch_op:
        batch_op.drop_index("ix_file_download_logs_tenant_created_at")
        batch_op.drop_column("action")

    with op.batch_alter_table("files") as batch_op:
        batch_op.drop_index("ix_files_tenant_object_key")
