"""OPS-71 срез-1: партии импорта и построчный отчёт (разд. 71.1).

Revision ID: 20260729_ops71_import_batch
Revises: 20260728_ops72_tenant_offboarding
Create Date: 2026-07-29

  * ``import_batch`` — применённая загрузка файла: цель, схема маппинга, счётчики
    и статус. Существует ради двух требований разд. 71.1, невыполнимых без неё:
    отката партии «по import batch id» и отчёта с привязкой к тому же id.
  * ``import_row`` — судьба каждой строки файла. У строк-обновлений лежит снимок
    ПРЕЖНИХ значений изменённых полей: без него откат может лишь удалить
    созданное, а вернуть перезаписанное будет неоткуда.

``import_row.entity_id`` намеренно БЕЗ внешнего ключа: цель импорта полиморфна
(сотрудники, должности, дальше — любая сущность реестра), а FK на «любую таблицу»
не существует. Пара ``entity_table`` + ``entity_id`` — то, по чему откат находит
запись, и она же переживает удаление цели из реестра (откат тогда честно откажет).

Обе таблицы tenant-scoped и армируются RLS В ЭТОЙ ЖЕ миграции (SEC-65):
реестр 277 → 279 enabled. Данных не мигрируем — таблицы новые.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260729_ops71_import_batch"
down_revision: str | Sequence[str] | None = "20260728_ops72_tenant_offboarding"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_RLS_TABLES = ("import_batch", "import_row")
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
        "import_batch",
        *_common_columns(),
        sa.Column("target", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="applied"),
        sa.Column("source_filename", sa.String(255), nullable=False),
        sa.Column("source_format", sa.String(16), nullable=False),
        sa.Column("mapping", sa.JSON(), nullable=False),
        sa.Column("total_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("notes", sa.JSON(), nullable=False),
        sa.Column("applied_by", sa.String(64), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rolled_back_by", sa.String(64), nullable=True),
        sa.Column("rolled_back_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_import_batch_tenant_id", "import_batch", ["tenant_id"])
    op.create_index("ix_import_batch_tenant_target", "import_batch", ["tenant_id", "target"])
    op.create_index("ix_import_batch_tenant_status", "import_batch", ["tenant_id", "status"])

    op.create_table(
        "import_row",
        *_common_columns(),
        sa.Column(
            "batch_id",
            sa.String(36),
            sa.ForeignKey("import_batch.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("natural_key", sa.String(512), nullable=True),
        sa.Column("entity_table", sa.String(64), nullable=True),
        sa.Column("entity_id", sa.String(36), nullable=True),
        sa.Column("before_values", sa.JSON(), nullable=False),
        sa.Column("errors", sa.JSON(), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
    )
    op.create_index("ix_import_row_tenant_id", "import_row", ["tenant_id"])
    op.create_index("ix_import_row_batch_id", "import_row", ["batch_id"])
    op.create_index("ix_import_row_batch_action", "import_row", ["batch_id", "action"])

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

    op.drop_index("ix_import_row_batch_action", table_name="import_row")
    op.drop_index("ix_import_row_batch_id", table_name="import_row")
    op.drop_index("ix_import_row_tenant_id", table_name="import_row")
    op.drop_table("import_row")

    op.drop_index("ix_import_batch_tenant_status", table_name="import_batch")
    op.drop_index("ix_import_batch_tenant_target", table_name="import_batch")
    op.drop_index("ix_import_batch_tenant_id", table_name="import_batch")
    op.drop_table("import_batch")
