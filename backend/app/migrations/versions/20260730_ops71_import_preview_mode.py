"""OPS-71 срез-5: режим партии — фоновый сухой прогон (разд. 71.1, строка «Dry-run»).

Revision ID: 20260730_ops71_import_preview_mode
Revises: 20260730_ops71_import_async
Create Date: 2026-07-30

Одна новая колонка у ``import_batch`` — таблиц не добавляется, реестр RLS не
меняется (279 enabled).

  * ``mode`` — ``apply`` (по умолчанию, как вели себя все прежние партии) либо
    ``preview``. Режим нужен именно как ПОЛЕ, а не как вывод из статуса: воркер
    должен знать, что делать, пока партия ещё ``pending``, то есть до появления
    терминального статуса.

Колонка NOT NULL с ``server_default='apply'``, поэтому существующие партии
остаются валидными и бэкфилл не нужен: они и были применяющими.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260730_ops71_import_preview_mode"
down_revision: str | Sequence[str] | None = "20260730_ops71_import_async"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "import_batch",
        sa.Column("mode", sa.String(8), nullable=False, server_default="apply"),
    )


def downgrade() -> None:
    op.drop_column("import_batch", "mode")
