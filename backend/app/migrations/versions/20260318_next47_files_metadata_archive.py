"""next47 files metadata archive fields

Revision ID: 20260318_next47_files_metadata_archive
Revises: 20260317_next46_content_search_archive
Create Date: 2026-03-18 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260318_next47_files_metadata_archive"
down_revision = "20260317_next46_content_search_archive"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("files", sa.Column("original_filename", sa.String(length=255), nullable=True))
    op.add_column("files", sa.Column("entity_type", sa.String(length=64), nullable=True))
    op.add_column("files", sa.Column("entity_id", sa.String(length=36), nullable=True))
    op.add_column(
        "files",
        sa.Column(
            "tags",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.create_index("ix_files_tenant_entity", "files", ["tenant_id", "entity_type", "entity_id"], unique=False)
    op.drop_index("ix_files_tenant_created_at", table_name="files")
    op.create_index("ix_files_tenant_updated_at", "files", ["tenant_id", "updated_at"], unique=False)
    op.execute("CREATE INDEX ix_files_tags_gin ON files USING GIN (tags)")


def downgrade() -> None:
    op.drop_index("ix_files_tags_gin", table_name="files")
    op.drop_index("ix_files_tenant_updated_at", table_name="files")
    op.create_index("ix_files_tenant_created_at", "files", ["tenant_id", "created_at"], unique=False)
    op.drop_index("ix_files_tenant_entity", table_name="files")
    op.drop_column("files", "tags")
    op.drop_column("files", "entity_id")
    op.drop_column("files", "entity_type")
    op.drop_column("files", "original_filename")
