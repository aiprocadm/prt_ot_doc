"""SEC-66 срез-1: журнал доступа к ПДн субъекта (152-ФЗ, разд. 66.2).

Revision ID: 20260723_sec66_pdn_access_log
Revises: 20260722_sec65_rls_documents
Create Date: 2026-07-23

Additive: одна новая таблица ``pdn_access_log``, бэкфилла нет (журнал начинается
с момента развёртывания). Enum не заводим — ``action`` это VARCHAR + whitelist
``PDN_ACCESS_ACTIONS`` в коде (конвенция budget/ppe/medical).

Таблица tenant-scoped, поэтому сразу армируется RLS (SEC-65) в том же ревизионном
шаге — иначе ratchet-гард ``scripts/audit/check_rls_coverage.py`` разошёлся бы с
реестром ``app/core/rls_policy.py``, где таблица числится в ``RLS_ENABLED_TABLES``.
RLS-часть, как и в ``20260722_sec65_rls_*``, включается только на PostgreSQL:
в SQLite такого механизма нет, поэтому основной тест-сьют её не видит.

Имя таблицы намеренно повторяется строковым литералом, а не константой: аудит
``scripts/audit/column_drift_lite.py`` разбирает миграции по AST и привязывает
колонки к таблице только при литерале в ``op.create_table`` (иначе
``test_audit_business_drift_reaches_zero`` считает таблицу необъявленной).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260723_sec66_pdn_access_log"
down_revision: str | Sequence[str] | None = "20260722_sec65_rls_documents"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_POLICY = "tenant_isolation"
_PREDICATE = (
    "current_setting('app.bypass_rls', true) = 'on' "
    "OR tenant_id = current_setting('app.current_tenant', true)"
)


def upgrade() -> None:
    op.create_table(
        "pdn_access_log",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("subject_person_id", sa.String(length=36), nullable=False),
        sa.Column("actor_user_id", sa.String(length=36), nullable=True),
        sa.Column("actor_email", sa.String(length=255), nullable=True),
        sa.Column("actor_role", sa.String(length=64), nullable=True),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("purpose", sa.String(length=255), nullable=True),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.ForeignKeyConstraint(["subject_person_id"], ["person.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_pdn_access_log_tenant_id"), "pdn_access_log", ["tenant_id"])
    op.create_index(
        "ix_pdn_access_log_tenant_subject_occurred",
        "pdn_access_log",
        ["tenant_id", "subject_person_id", "occurred_at"],
    )

    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute('ALTER TABLE "pdn_access_log" ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE "pdn_access_log" FORCE ROW LEVEL SECURITY')
    op.execute(
        f'CREATE POLICY "{_POLICY}" ON "pdn_access_log" '
        f"FOR ALL USING ({_PREDICATE}) WITH CHECK ({_PREDICATE})"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(f'DROP POLICY IF EXISTS "{_POLICY}" ON "pdn_access_log"')
        op.execute('ALTER TABLE "pdn_access_log" NO FORCE ROW LEVEL SECURITY')
        op.execute('ALTER TABLE "pdn_access_log" DISABLE ROW LEVEL SECURITY')
    op.drop_index("ix_pdn_access_log_tenant_subject_occurred", table_name="pdn_access_log")
    op.drop_index(op.f("ix_pdn_access_log_tenant_id"), table_name="pdn_access_log")
    op.drop_table("pdn_access_log")
