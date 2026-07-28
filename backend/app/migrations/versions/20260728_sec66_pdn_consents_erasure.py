"""SEC-66 срез-2: согласия субъекта ПДн, запись об обезличивании, отметка на Person.

Revision ID: 20260728_sec66_pdn_consents_erasure
Revises: 20260728_sec65_rls_model_less_tables
Create Date: 2026-07-28

Разд. 66.1 «хранение и версионирование согласий» + разд. 66.2 «удаление / отзыв
согласия: анонимизация или удаление, при этом сохранение обезличенных данных,
где требует закон».

  * ``pdn_consent`` — версии согласий. UNIQUE(tenant_id, subject_person_id,
    purpose, consent_version): перевыдача создаёт новую версию, прежняя уходит в
    ``superseded``; отзыв ставит ``withdrawn``. Строки не удаляются — правомерность
    прошлой обработки доказывается только неизменной историей.
  * ``pdn_erasure_record`` — что вычищено и что сохранено обезличенным. Без этой
    записи на вопрос субъекта «удалили ли мои данные» ответить нечем: само
    обезличивание необратимо и следов в данных не оставляет.
  * ``person.anonymized_at`` — отметка обезличивания. NULLABLE без бэкфилла:
    существующие субъекты не обезличены.

Обе таблицы tenant-scoped, поэтому армируются RLS В ЭТОЙ ЖЕ миграции (SEC-65):
ратчет-гард ``scripts/audit/check_rls_coverage.py`` не пропустит новую
tenant-таблицу без решения, и появиться неармированной она не должна даже на один
релиз. Реестр: 272 → 274 enabled.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260728_sec66_pdn_consents_erasure"
down_revision: str | Sequence[str] | None = "20260728_sec65_rls_model_less_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_RLS_TABLES = ("pdn_consent", "pdn_erasure_record")
_POLICY = "tenant_isolation"
_PREDICATE = (
    "current_setting('app.bypass_rls', true) = 'on' "
    "OR tenant_id = current_setting('app.current_tenant', true)"
)


def upgrade() -> None:
    op.create_table(
        "pdn_consent",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.String(36),
            sa.ForeignKey("tenant.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "subject_person_id",
            sa.String(36),
            sa.ForeignKey("person.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("purpose", sa.String(64), nullable=False),
        sa.Column("legal_basis", sa.String(32), nullable=False, server_default="consent"),
        sa.Column("consent_version", sa.Integer(), nullable=False, server_default="1"),
        # ``version`` — колонка оптимистичной блокировки из TenantBaseModel.
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("document_ref", sa.String(255), nullable=True),
        sa.Column("text_sha256", sa.String(64), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("withdrawal_reason", sa.Text(), nullable=True),
        sa.Column(
            "recorded_by_user_id",
            sa.String(36),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("recorded_by_email", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "tenant_id",
            "subject_person_id",
            "purpose",
            "consent_version",
            name="uq_pdn_consent_subject_purpose_version",
        ),
    )
    op.create_index(
        "ix_pdn_consent_tenant_subject_purpose",
        "pdn_consent",
        ["tenant_id", "subject_person_id", "purpose"],
    )

    op.create_table(
        "pdn_erasure_record",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.String(36),
            sa.ForeignKey("tenant.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "subject_person_id",
            sa.String(36),
            sa.ForeignKey("person.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("pseudonym", sa.String(64), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("scrubbed_fields", sa.JSON(), nullable=False),
        sa.Column("retained_sections", sa.JSON(), nullable=False),
        sa.Column("performed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "performed_by_user_id",
            sa.String(36),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("performed_by_email", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_pdn_erasure_record_tenant_subject",
        "pdn_erasure_record",
        ["tenant_id", "subject_person_id"],
    )

    op.add_column("person", sa.Column("anonymized_at", sa.DateTime(timezone=True), nullable=True))

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

    op.drop_column("person", "anonymized_at")
    op.drop_index("ix_pdn_erasure_record_tenant_subject", table_name="pdn_erasure_record")
    op.drop_table("pdn_erasure_record")
    op.drop_index("ix_pdn_consent_tenant_subject_purpose", table_name="pdn_consent")
    op.drop_table("pdn_consent")
