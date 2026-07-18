"""Add tenancy hierarchy metadata and quotas.

Revision ID: 20250601_tenant_quotas_and_counters
Revises: 20250501_reliability_outbox_webhook_delivery
Create Date: 2025-06-01 00:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20250601_tenant_quotas_and_counters"
down_revision: Union[str, None] = "20250501_reliability_outbox_webhook_delivery"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tenant", sa.Column("code", sa.String(length=64), nullable=True))
    op.add_column("tenant", sa.Column("parent_id", sa.String(length=36), nullable=True))
    op.add_column("tenant", sa.Column("kind", sa.Enum("customer", "branch", "contractor", name="tenantkind"), nullable=True))
    op.add_column("tenant", sa.Column("schema_name", sa.String(length=128), nullable=True))
    op.create_foreign_key("fk_tenant_parent", "tenant", "tenant", ["parent_id"], ["id"])
    op.create_unique_constraint("uq_tenants_code", "tenant", ["code"])
    op.create_unique_constraint("uq_tenants_schema_name", "tenant", ["schema_name"])
    op.create_index("ix_tenants_parent_id", "tenant", ["parent_id"], unique=False)
    op.create_index("ix_tenants_kind", "tenant", ["kind"], unique=False)

    op.execute("UPDATE tenant SET code = slug WHERE code IS NULL")
    op.execute("UPDATE tenant SET kind = 'customer' WHERE kind IS NULL")
    op.execute("UPDATE tenant SET schema_name = CONCAT('tenant_', slug) WHERE schema_name IS NULL")

    with op.batch_alter_table("tenant") as batch:
        batch.alter_column("code", existing_type=sa.String(length=64), nullable=False)
        batch.alter_column("kind", existing_type=sa.Enum("customer", "branch", "contractor", name="tenantkind"), nullable=False)
        batch.alter_column("schema_name", existing_type=sa.String(length=128), nullable=False)

    op.create_table(
        "tenant_quotas",
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("max_parallel_jobs", sa.Integer(), nullable=False, server_default=sa.text("4")),
        sa.Column("max_doc_generations_per_month", sa.Integer(), nullable=False, server_default=sa.text("5000")),
        sa.Column("max_storage_mb", sa.Integer(), nullable=False, server_default=sa.text("10240")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("id", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id"),
    )

    op.create_table(
        "tenant_counters",
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("yyyymm", sa.String(length=6), nullable=False),
        sa.Column("doc_generations", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("id", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "yyyymm", name="uq_tenant_counter_period"),
    )
    op.create_index("ix_tenant_counters_tenant_id", "tenant_counters", ["tenant_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_tenant_counters_tenant_id", table_name="tenant_counters")
    op.drop_table("tenant_counters")
    op.drop_table("tenant_quotas")
    op.drop_index("ix_tenants_kind", table_name="tenant")
    op.drop_index("ix_tenants_parent_id", table_name="tenant")
    op.drop_constraint("uq_tenants_schema_name", "tenant", type_="unique")
    op.drop_constraint("uq_tenants_code", "tenant", type_="unique")
    op.drop_constraint("fk_tenant_parent", "tenant", type_="foreignkey")
    op.drop_column("tenant", "schema_name")
    op.drop_column("tenant", "kind")
    op.drop_column("tenant", "parent_id")
    op.drop_column("tenant", "code")
    op.execute("DROP TYPE IF EXISTS tenantkind")
