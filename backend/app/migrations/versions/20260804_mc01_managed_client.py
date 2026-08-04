"""mc01: managed_client — ведомые клиенты аутсорсера (BIZ-49 срез-1, разд. 49.1).

Additive. Таблица tenant-scoped, поэтому RLS вооружается ЗДЕСЬ ЖЕ (урок волны
cmt03: новая tenant-таблица без записи в реестре RLS = красный сторож на main).
Ссылка на арендатора клиента — слугом, без cross-schema FK.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260804_mc01_managed_client"
down_revision = "20260803_ops73_api_deprecation_usage"
branch_labels = None
depends_on = None

_TABLE = "managed_client"
_POLICY = "tenant_isolation"
_PREDICATE = (
    "current_setting('app.bypass_rls', true) = 'on' "
    "OR tenant_id = current_setting('app.current_tenant', true)"
)

_MODE = postgresql.ENUM("lightweight", "dedicated", name="managedclientmode", create_type=False)
_CONTRACT_STATUS = postgresql.ENUM(
    "draft",
    "active",
    "suspended",
    "terminated",
    name="managedclientcontractstatus",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"
    if is_pg:
        _MODE.create(bind, checkfirst=True)
        _CONTRACT_STATUS.create(bind, checkfirst=True)

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
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("mode", _MODE if is_pg else sa.String(length=32), nullable=False),
        sa.Column(
            "company_id",
            sa.String(length=36),
            sa.ForeignKey("company.id", ondelete="RESTRICT"),
            nullable=True,
            index=True,
        ),
        sa.Column("dedicated_tenant_slug", sa.String(length=64), nullable=True),
        sa.Column(
            "contract_status",
            _CONTRACT_STATUS if is_pg else sa.String(length=32),
            nullable=False,
            server_default="draft",
        ),
        sa.Column("contract_no", sa.String(length=128), nullable=True),
        sa.Column("contract_starts_at", sa.Date(), nullable=True),
        sa.Column("contract_ends_at", sa.Date(), nullable=True),
        sa.Column(
            "responsible_person_id",
            sa.String(length=36),
            sa.ForeignKey("person.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.UniqueConstraint("tenant_id", "name", name="uq_managed_client_name"),
    )
    op.create_index("ix_managed_client_tenant_status", _TABLE, ["tenant_id", "contract_status"])

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
    op.drop_index("ix_managed_client_tenant_status", table_name=_TABLE)
    op.drop_table(_TABLE)
    if is_pg:
        _CONTRACT_STATUS.drop(bind, checkfirst=True)
        _MODE.drop(bind, checkfirst=True)
