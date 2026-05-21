"""Create regulatory_inspection base table (restoration of missing history step).

Revision ID: 20250415_create_regulatory_inspection_base
Revises: 20250410_p1_entities_tasks_roles
Create Date: 2025-04-15 00:00:00.000000

This migration was originally missing from the alembic history — migration
``20250420_p1_obligations_inspections_attestations`` expected the table to
exist (it does ``op.add_column("regulatory_inspection", ...)``) but no
prior step created it. The defect was masked while CI was offline during
the 2026-03-21..2026-05-21 billing block, then surfaced when PG migrations
re-ran on PR #551 as:

    asyncpg.exceptions.UndefinedTableError:
    relation "regulatory_inspection" does not exist

SQLite environments silently passed because ``add_column`` on a missing
table is rejected by Alembic-batch but the table was likely created
implicitly via ``Base.metadata.create_all()`` in dev bootstrap (a code
path that does not record alembic state). Inserting this base-creation
step here restores the implied chain. Columns track the ``Inspection``
ORM model (table ``regulatory_inspection``) in ``backend/app/models/models.py``
sans the three columns that 20250420 was always meant to add
(``inspection_type``, ``responsible_id``, ``recurrence_rule``).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "20250415_create_regulatory_inspection_base"
down_revision: str | tuple[str, ...] = "20250410_p1_entities_tasks_roles"
branch_labels: str | None = None
depends_on: str | None = None


_INSPECTION_STATUS = sa.Enum(
    "PLANNED",
    "IN_PROGRESS",
    "COMPLETED",
    "CANCELLED",
    name="regulatoryinspectionstatus",
    # We create/drop the type explicitly in upgrade/downgrade. Default
    # ``create_type=True`` would make ``op.create_table`` also try to
    # create the type during column emission — a second CREATE TYPE
    # without checkfirst that fails on PostgreSQL with
    # ``DuplicateObjectError: type already exists``.
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        _INSPECTION_STATUS.create(bind, checkfirst=True)

    op.create_table(
        "regulatory_inspection",
        # TenantBaseModel base columns
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        # SoftDeleteMixin
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        # Domain columns (matches Inspection model in backend/app/models/models.py)
        sa.Column("company_id", sa.String(length=36), nullable=False),
        sa.Column("site_id", sa.String(length=36), nullable=True),
        sa.Column("authority", sa.String(length=255), nullable=False),
        sa.Column("purpose", sa.String(length=255), nullable=True),
        sa.Column("scheduled_at", sa.Date(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            _INSPECTION_STATUS,
            nullable=False,
            server_default="PLANNED",
        ),
        sa.Column("result_summary", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["company_id"], ["company.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["site_id"], ["site.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_regulatory_inspection_tenant_id",
        "regulatory_inspection",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        "ix_regulatory_inspection_company_id",
        "regulatory_inspection",
        ["company_id"],
        unique=False,
    )
    op.create_index(
        "ix_regulatory_inspection_site_id",
        "regulatory_inspection",
        ["site_id"],
        unique=False,
    )
    op.create_index(
        "ix_regulatory_inspection_company",
        "regulatory_inspection",
        ["tenant_id", "company_id"],
        unique=False,
    )
    op.create_index(
        "ix_regulatory_inspection_site",
        "regulatory_inspection",
        ["tenant_id", "site_id"],
        unique=False,
    )
    op.create_index(
        "ix_regulatory_inspection_status",
        "regulatory_inspection",
        ["tenant_id", "status"],
        unique=False,
    )


def downgrade() -> None:
    bind = op.get_bind()
    op.drop_index("ix_regulatory_inspection_status", table_name="regulatory_inspection")
    op.drop_index("ix_regulatory_inspection_site", table_name="regulatory_inspection")
    op.drop_index("ix_regulatory_inspection_company", table_name="regulatory_inspection")
    op.drop_index("ix_regulatory_inspection_site_id", table_name="regulatory_inspection")
    op.drop_index("ix_regulatory_inspection_company_id", table_name="regulatory_inspection")
    op.drop_index("ix_regulatory_inspection_tenant_id", table_name="regulatory_inspection")
    op.drop_table("regulatory_inspection")
    if bind.dialect.name == "postgresql":
        _INSPECTION_STATUS.drop(bind, checkfirst=True)
