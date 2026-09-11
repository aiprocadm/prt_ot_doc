"""B.18 (разд. 19.2): реестр требований — обязательное ядро арендатора.

Revision ID: 20260911_b18_compliance_requirements
Revises: 20260911_b18_npabinding_reviewed_rev
Create Date: 2026-09-11

  * ``compliance_requirement`` — что арендатор ОБЯЗАН делать по НПА: откуда
    требование (акт и пункт общего реестра), к кому относится (роль /
    площадка / процесс), кто отвечает, как часто и до какой даты, насколько
    серьёзно неисполнение. UNIQUE(tenant_id, code): код требования —
    естественный ключ для ссылок и импорта.
  * ``compliance_requirement_evidence`` — доказательства исполнения: документ
    и/или заметка, кто и когда подтвердил. Подтверждение сдвигает контрольную
    дату на период; разовое требование — закрывает.

Ссылки в общий реестр (``npa_id`` → ``npa_act.id``, ``clause_id`` →
``npa_clause.id``) оформлены ключами ЗДЕСЬ, а не в ORM: ключ tenant→shared в
модели ломает ``create_all`` (прецедент ``NPABinding.npa_id``). ON DELETE SET
NULL: акт из реестра не удаляется, но если удалят — требование останется,
потеряв только ссылку.

Обе таблицы tenant-scoped и армируются RLS в этой же миграции (SEC-65).
Данных не мигрируем — таблицы новые.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260911_b18_compliance_requirements"
down_revision: str | Sequence[str] | None = "20260911_b18_npabinding_reviewed_rev"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_RLS_TABLES = ("compliance_requirement", "compliance_requirement_evidence")
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
        "compliance_requirement",
        *_common_columns(),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "npa_id",
            sa.String(36),
            sa.ForeignKey("npa_act.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "clause_id",
            sa.String(36),
            sa.ForeignKey("npa_clause.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("role_code", sa.String(64), nullable=True),
        sa.Column(
            "site_id", sa.String(36), sa.ForeignKey("site.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("process_code", sa.String(64), nullable=True),
        sa.Column(
            "owner_user_id",
            sa.String(36),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("periodicity_days", sa.Integer(), nullable=True),
        sa.Column("next_due_at", sa.Date(), nullable=True),
        sa.Column("last_confirmed_at", sa.Date(), nullable=True),
        sa.Column("severity", sa.String(16), nullable=False, server_default="medium"),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("tenant_id", "code", name="uq_compliance_requirement_code"),
    )
    op.create_index("ix_compliance_requirement_npa_id", "compliance_requirement", ["npa_id"])
    op.create_index(
        "ix_compliance_requirement_owner_user_id", "compliance_requirement", ["owner_user_id"]
    )
    op.create_index(
        "ix_compliance_requirement_tenant_status",
        "compliance_requirement",
        ["tenant_id", "status"],
    )
    op.create_index(
        "ix_compliance_requirement_tenant_due",
        "compliance_requirement",
        ["tenant_id", "next_due_at"],
    )

    op.create_table(
        "compliance_requirement_evidence",
        *_common_columns(),
        sa.Column(
            "requirement_id",
            sa.String(36),
            sa.ForeignKey("compliance_requirement.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "document_id",
            sa.String(36),
            sa.ForeignKey("document.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("confirmed_at", sa.Date(), nullable=False),
        sa.Column(
            "confirmed_by",
            sa.String(36),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_compliance_requirement_evidence_requirement_id",
        "compliance_requirement_evidence",
        ["requirement_id"],
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
        "ix_compliance_requirement_evidence_requirement_id",
        table_name="compliance_requirement_evidence",
    )
    op.drop_table("compliance_requirement_evidence")
    op.drop_index("ix_compliance_requirement_tenant_due", table_name="compliance_requirement")
    op.drop_index("ix_compliance_requirement_tenant_status", table_name="compliance_requirement")
    op.drop_index("ix_compliance_requirement_owner_user_id", table_name="compliance_requirement")
    op.drop_index("ix_compliance_requirement_npa_id", table_name="compliance_requirement")
    op.drop_table("compliance_requirement")
