"""rs03: tenant_legal_document — юр. тексты арендатора (BIZ-52 срез-5).

Доп. №1 разд. 52.2, четвёртый пункт: «свои юридические тексты (оферта, политика
ПДн, согласия) на уровне reseller'а». Additive: новая таблица, существующие
данные не трогаются.

Tenant-таблица, поэтому RLS вооружается ЗДЕСЬ ЖЕ (правило проекта, урок cmt03).
Чтение текста ПАРТНЁРА клиентом идёт доверенной сессией в прикладном коде:
строка принадлежит другому арендатору, а публичная оферта — то, что и так
показывают каждому.

Revision ID: 20260812_rs03_tenant_legal_document
Revises: 20260812_rs02_tenant_branding
Create Date: 2026-08-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260812_rs03_tenant_legal_document"
down_revision = "20260812_rs02_tenant_branding"
branch_labels = None
depends_on = None

_TABLE = "tenant_legal_document"
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
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("doc_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
    )
    # Две «версии 3» одного вида превратили бы вопрос «что действует сейчас» в
    # выбор из нескольких строк — для юридического текста это недопустимо.
    op.create_unique_constraint(
        "uq_tenant_legal_kind_version", _TABLE, ["tenant_id", "kind", "doc_version"]
    )
    op.create_index("ix_tenant_legal_kind", _TABLE, ["tenant_id", "kind", "doc_version"])

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
    op.drop_index("ix_tenant_legal_kind", table_name=_TABLE)
    op.drop_constraint("uq_tenant_legal_kind_version", _TABLE, type_="unique")
    op.drop_table(_TABLE)
