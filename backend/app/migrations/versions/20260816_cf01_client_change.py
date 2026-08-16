"""cf01: client_change — лента изменений у клиента (BIZ-51 срез-1).

Доп. №1 разд. 51.1. Additive: новая таблица, существующие данные не трогаются.

Tenant-таблица, поэтому RLS вооружается ЗДЕСЬ ЖЕ (правило проекта, урок cmt03).

Revision ID: 20260816_cf01_client_change
Revises: 20260814_rs05_tenant_legal_acceptance
Create Date: 2026-08-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260816_cf01_client_change"
down_revision = "20260814_rs05_tenant_legal_acceptance"
branch_labels = None
depends_on = None

_TABLE = "client_change"
_POLICY = "tenant_isolation"
_PREDICATE = (
    "current_setting('app.bypass_rls', true) = 'on' "
    "OR tenant_id = current_setting('app.current_tenant', true)"
)

_KINDS = (
    "employee_hired",
    "employee_left",
    "position_added",
    "site_added",
    "org_structure_changed",
    "activity_changed",
    "deadline_approaching",
    "regulation_changed",
)
_STATUSES = ("new", "handled", "dismissed")

# `create_type=False` — как в соседних миграциях (mc01, cmt01): иначе
# `create_table` пытается создать тип ВТОРОЙ раз, поверх созданного явно, и
# падает с «type already exists». Поймано db-гейтом на живом PostgreSQL.
_KIND = postgresql.ENUM(*_KINDS, name="clientchangekind", create_type=False)
_STATUS = postgresql.ENUM(*_STATUSES, name="clientchangestatus", create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    if is_pg:
        _KIND.create(bind, checkfirst=True)
        _STATUS.create(bind, checkfirst=True)

    op.create_table(
        _TABLE,
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
            "managed_client_id",
            sa.String(length=36),
            sa.ForeignKey("managed_client.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", _KIND if is_pg else sa.String(length=32), nullable=False),
        sa.Column("happened_on", sa.Date(), nullable=False),
        sa.Column("summary", sa.String(length=255), nullable=False),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column(
            "status",
            _STATUS if is_pg else sa.String(length=16),
            nullable=False,
            server_default="new",
        ),
        sa.Column(
            "handled_by",
            sa.String(length=36),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("handled_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Лента читается по клиенту и в обратном хронологическом порядке.
    op.create_index(
        "ix_client_change_feed", _TABLE, ["tenant_id", "managed_client_id", "happened_on"]
    )

    if not is_pg:
        return
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute(f'ALTER TABLE "{_TABLE}" ENABLE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE "{_TABLE}" FORCE ROW LEVEL SECURITY')
    op.execute(
        f'CREATE POLICY "{_POLICY}" ON "{_TABLE}" '
        f"FOR ALL USING ({_PREDICATE}) WITH CHECK ({_PREDICATE})"
    )


def downgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"
    if is_pg:
        op.execute(f'DROP POLICY IF EXISTS "{_POLICY}" ON "{_TABLE}"')
    op.drop_index("ix_client_change_feed", table_name=_TABLE)
    op.drop_table(_TABLE)
    if is_pg:
        sa.Enum(name="clientchangekind").drop(bind, checkfirst=True)
        sa.Enum(name="clientchangestatus").drop(bind, checkfirst=True)
