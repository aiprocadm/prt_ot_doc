"""rs05: tenant_legal_acceptance — кто принял юр. текст (BIZ-52 срез-11).

Доп. №1 разд. 52.2: срез-5 научил партнёра публиковать оферту, политику ПДн и
текст согласия, но КТО и КОГДА их принял не записывалось нигде. Additive: новая
таблица, существующие данные не трогаются.

Tenant-таблица, поэтому RLS вооружается ЗДЕСЬ ЖЕ (правило проекта, урок cmt03).

Revision ID: 20260814_rs05_tenant_legal_acceptance
Revises: 20260812_rs04_tenant_branding_images
Create Date: 2026-08-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260814_rs05_tenant_legal_acceptance"
down_revision = "20260812_rs04_tenant_branding_images"
branch_labels = None
depends_on = None

_TABLE = "tenant_legal_acceptance"
_POLICY = "tenant_isolation"
_PREDICATE = (
    "current_setting('app.bypass_rls', true) = 'on' "
    "OR tenant_id = current_setting('app.current_tenant', true)"
)


def upgrade() -> None:
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
        sa.Column(
            "user_id",
            sa.String(length=36),
            sa.ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("doc_version", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("body_sha256", sa.String(length=64), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=False),
    )
    # Двойное нажатие кнопки не должно превращать «когда принял» в выбор из
    # нескольких ответов.
    op.create_unique_constraint(
        "uq_tenant_legal_acceptance_user_kind_version",
        _TABLE,
        ["tenant_id", "user_id", "kind", "doc_version"],
    )
    op.create_index(
        "ix_tenant_legal_acceptance_lookup", _TABLE, ["tenant_id", "user_id", "kind"]
    )

    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
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
    if bind.dialect.name == "postgresql":
        op.execute(f'DROP POLICY IF EXISTS "{_POLICY}" ON "{_TABLE}"')
    op.drop_index("ix_tenant_legal_acceptance_lookup", table_name=_TABLE)
    op.drop_constraint(
        "uq_tenant_legal_acceptance_user_kind_version", _TABLE, type_="unique"
    )
    op.drop_table(_TABLE)
