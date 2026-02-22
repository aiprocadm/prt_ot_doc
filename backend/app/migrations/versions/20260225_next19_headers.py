"""NEXT-19 header/footer presets

Revision ID: 20260225_next19
Revises: 20260224_next18
Create Date: 2026-02-25
"""

from alembic import op
import sqlalchemy as sa


revision = "20260225_next19"
down_revision = "20260224_next18"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "header_footer_presets",
        sa.Column("code", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("different_first", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("different_odd_even", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("header_first_xml", sa.Text(), nullable=True),
        sa.Column("header_odd_xml", sa.Text(), nullable=True),
        sa.Column("header_even_xml", sa.Text(), nullable=True),
        sa.Column("footer_first_xml", sa.Text(), nullable=True),
        sa.Column("footer_odd_xml", sa.Text(), nullable=True),
        sa.Column("footer_even_xml", sa.Text(), nullable=True),
        sa.Column("watermark", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_header_footer_preset_tenant_code"),
    )
    op.create_index("ix_header_footer_preset_tenant_code", "header_footer_presets", ["tenant_id", "code"])
    op.create_index("ix_header_footer_preset_updated_at", "header_footer_presets", ["updated_at"])


def downgrade() -> None:
    op.drop_index("ix_header_footer_preset_updated_at", table_name="header_footer_presets")
    op.drop_index("ix_header_footer_preset_tenant_code", table_name="header_footer_presets")
    op.drop_table("header_footer_presets")
