"""br01: RC-014 — dedicated Branch entity separated from Site (additive).

Создаёт таблицу ``branch`` (филиал: уровень master-data между Company и Site,
vNext-иерархия «компании → филиалы → объекты») и добавляет ``site.branch_id``
— nullable app-level ссылку БЕЗ DB FK (add_column с FK — класс граблей wa02;
прецедент: contractor_registry.company_id). ``status`` — VARCHAR, не PG-enum
(снимает класс enum-parity, прецедент cm01).

Имена таблиц ЛИТЕРАЛОМ (AST-audit blindspot). Honest downgrade удаляет
индекс/колонку/таблицу в обратном порядке.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260702_br01_branch_entity"
down_revision = "20260626_so03_sout_norm_bridges"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "branch",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.String(length=36),
            sa.ForeignKey("tenant.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "company_id",
            sa.String(length=36),
            sa.ForeignKey("company.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=True),
        sa.Column("address", sa.String(length=255), nullable=True),
        sa.Column("contact_name", sa.String(length=255), nullable=True),
        sa.Column("contact_phone", sa.String(length=32), nullable=True),
        sa.Column("contact_email", sa.String(length=320), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.UniqueConstraint("tenant_id", "company_id", "name", name="uq_branch_company_name"),
    )
    op.add_column("site", sa.Column("branch_id", sa.String(length=36), nullable=True))
    op.create_index("ix_site_branch_id", "site", ["branch_id"])


def downgrade() -> None:
    op.drop_index("ix_site_branch_id", table_name="site")
    op.drop_column("site", "branch_id")
    op.drop_table("branch")
