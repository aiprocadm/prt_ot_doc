"""SEC-66 срез-3: реестр обработки ПДн и договоры поручения (разд. 66.1, 66.3).

Revision ID: 20260728_sec66_pdn_registry_dpa
Revises: 20260728_sec66_pdn_consents_erasure
Create Date: 2026-07-28

  * ``pdn_processing_activity`` — реестр обработки «как данные в системе, не в
    Excel»: какие ПДн, цель и основание, срок хранения ВМЕСТЕ с нормой, кто имеет
    доступ, получатели, локализация. UNIQUE(tenant_id, code): код процесса —
    естественный ключ, повторная отправка обновляет строку, а не падает.
  * ``pdn_processing_agreement`` — договоры поручения и роли Оператор/Обработчик.
    Роль хранится У ДОГОВОРА, а не у арендатора: один и тот же арендатор бывает
    Оператором по отношению к своим сотрудникам и Обработчиком по отношению к
    клиенту, которого обслуживает (аутсорсинг).

Обе таблицы tenant-scoped и армируются RLS В ЭТОЙ ЖЕ миграции (SEC-65): реестр
274 → 276 enabled. Данных не мигрируем — таблицы новые.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260728_sec66_pdn_registry_dpa"
down_revision: str | Sequence[str] | None = "20260728_sec66_pdn_consents_erasure"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_RLS_TABLES = ("pdn_processing_activity", "pdn_processing_agreement")
_POLICY = "tenant_isolation"
_PREDICATE = (
    "current_setting('app.bypass_rls', true) = 'on' "
    "OR tenant_id = current_setting('app.current_tenant', true)"
)


def _common_columns() -> list[sa.Column]:
    return [
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.String(36),
            sa.ForeignKey("tenant.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # ``version`` — оптимистичная блокировка из TenantBaseModel.
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "pdn_processing_activity",
        *_common_columns(),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("purpose", sa.String(64), nullable=False),
        sa.Column("purpose_description", sa.Text(), nullable=True),
        sa.Column("legal_basis", sa.String(32), nullable=False, server_default="consent"),
        sa.Column("data_categories", sa.JSON(), nullable=False),
        sa.Column("subject_categories", sa.JSON(), nullable=False),
        sa.Column("retention_months", sa.Integer(), nullable=True),
        sa.Column("retention_basis", sa.String(255), nullable=True),
        sa.Column("access_roles", sa.JSON(), nullable=False),
        sa.Column("recipients", sa.JSON(), nullable=False),
        sa.Column("storage_location", sa.String(64), nullable=False, server_default="RU"),
        sa.Column(
            "cross_border_transfer", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("review_at", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.UniqueConstraint("tenant_id", "code", name="uq_pdn_processing_activity_code"),
    )
    op.create_index(
        "ix_pdn_processing_activity_tenant_active",
        "pdn_processing_activity",
        ["tenant_id", "is_active"],
    )

    op.create_table(
        "pdn_processing_agreement",
        *_common_columns(),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("party_role", sa.String(16), nullable=False),
        sa.Column("counterparty_name", sa.String(255), nullable=False),
        sa.Column("counterparty_inn", sa.String(32), nullable=True),
        sa.Column("counterparty_tenant_slug", sa.String(64), nullable=True),
        sa.Column("document_ref", sa.String(255), nullable=True),
        sa.Column("signed_at", sa.Date(), nullable=True),
        sa.Column("valid_until", sa.Date(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column(
            "subprocessing_allowed", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("breach_notification_hours", sa.Integer(), nullable=True),
        sa.Column("covered_activity_codes", sa.JSON(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("terminated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_pdn_processing_agreement_tenant_status",
        "pdn_processing_agreement",
        ["tenant_id", "status"],
    )

    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("SET LOCAL lock_timeout = '5s'")
    for table in _RLS_TABLES:
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
        op.execute(
            f'CREATE POLICY "{_POLICY}" ON "{table}" '
            f"FOR ALL USING ({_PREDICATE}) WITH CHECK ({_PREDICATE})"
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for table in reversed(_RLS_TABLES):
            op.execute(f'DROP POLICY IF EXISTS "{_POLICY}" ON "{table}"')

    op.drop_index(
        "ix_pdn_processing_agreement_tenant_status", table_name="pdn_processing_agreement"
    )
    op.drop_table("pdn_processing_agreement")
    op.drop_index(
        "ix_pdn_processing_activity_tenant_active", table_name="pdn_processing_activity"
    )
    op.drop_table("pdn_processing_activity")
