"""NEXT-18 template core fields and constraints

Revision ID: 20260224_next18
Revises: 20260223_next15
Create Date: 2026-02-24
"""

from alembic import op
import sqlalchemy as sa


revision = "20260224_next18"
down_revision = "20260223_next15"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("template", sa.Column("code", sa.String(length=255), nullable=True))
    op.add_column("template", sa.Column("domain", sa.String(length=255), nullable=True))
    op.add_column("template", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))

    op.execute("UPDATE template SET code = name WHERE code IS NULL")
    op.alter_column("template", "code", nullable=False)

    op.create_unique_constraint("uq_templates_tenant_code", "template", ["tenant_id", "code"])

    op.add_column("templateversion", sa.Column("sha256", sa.String(length=64), nullable=True))
    op.add_column("templateversion", sa.Column("file_id", sa.String(length=512), nullable=True))
    op.add_column("templateversion", sa.Column("placeholder_index", sa.JSON(), nullable=True))
    op.add_column("templateversion", sa.Column("created_by", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("templateversion", "created_by")
    op.drop_column("templateversion", "placeholder_index")
    op.drop_column("templateversion", "file_id")
    op.drop_column("templateversion", "sha256")

    op.drop_constraint("uq_templates_tenant_code", "template", type_="unique")
    op.drop_column("template", "deleted_at")
    op.drop_column("template", "domain")
    op.drop_column("template", "code")
