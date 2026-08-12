"""rs02: tenant_branding — бренд ПРИЛОЖЕНИЯ на уровне арендатора (BIZ-52 срез-4).

Доп. №1 разд. 52.2: white-label всего приложения, а не только документов.
Additive: новая таблица, существующие данные не трогаются, у всех арендаторов
до заполнения действует бренд платформы.

Tenant-таблица, поэтому RLS вооружается ЗДЕСЬ ЖЕ (правило проекта, урок cmt03).
Чтение бренда ПАРТНЁРА клиентом идёт через доверенную сессию в прикладном коде:
бренд — то, что и так показывают всем, но строка принадлежит другому
арендатору, и обычная сессия под FORCE RLS её не увидит.

Все содержательные колонки nullable: незаполненное поле означает «не задано» и
наследуется вверх по цепочке (свой → партнёра → платформа). Проставь им
умолчания — и наследование оборвалось бы у каждого, кто задал хотя бы одно поле.

Revision ID: 20260812_rs02_tenant_branding
Revises: 20260811_rs01_tenant_kind_reseller
Create Date: 2026-08-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260812_rs02_tenant_branding"
down_revision = "20260811_rs01_tenant_kind_reseller"
branch_labels = None
depends_on = None

_TABLE = "tenant_branding"
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
        sa.Column("app_name", sa.String(length=120), nullable=True),
        sa.Column("primary_color", sa.String(length=32), nullable=True),
        sa.Column("support_email", sa.String(length=255), nullable=True),
    )
    # Один бренд на арендатора: дубль строки сделал бы ответ ручки
    # неопределённым — какой из двух брендов действующий.
    op.create_unique_constraint("uq_tenant_branding_tenant", _TABLE, ["tenant_id"])

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
    op.drop_constraint("uq_tenant_branding_tenant", _TABLE, type_="unique")
    op.drop_table(_TABLE)
