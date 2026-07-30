"""OPS-71 срез-2: асинхронный импорт с прогрессом (разд. 71.1, строка «Прогресс»).

Revision ID: 20260730_ops71_import_async
Revises: 20260729_ops71_import_batch
Create Date: 2026-07-30

Только новые колонки у ``import_batch`` — таблиц не добавляется, поэтому реестр
RLS не меняется (279 enabled). Все колонки nullable либо с server_default, так
что существующие партии остаются валидными и бэкфилл не нужен.

  * ``processed_rows`` — сколько строк уже обработано (прогресс).
  * ``source_key`` — ключ исходного файла в хранилище: воркер живёт в другом
    процессе, и тело HTTP-запроса ему недоступно.
  * ``error_message`` — причина обрыва; ``failed`` без причины отправляет
    человека читать логи воркера.
  * ``finished_at`` — момент завершения. ``applied_at`` остаётся моментом
    ПОСТАНОВКИ: делать его nullable значило бы сломать уже опубликованный
    контракт ответа ради переименования.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260730_ops71_import_async"
down_revision: str | Sequence[str] | None = "20260729_ops71_import_batch"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "import_batch",
        sa.Column("processed_rows", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("import_batch", sa.Column("source_key", sa.String(512), nullable=True))
    op.add_column("import_batch", sa.Column("error_message", sa.Text(), nullable=True))
    op.add_column(
        "import_batch", sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("import_batch", "finished_at")
    op.drop_column("import_batch", "error_message")
    op.drop_column("import_batch", "source_key")
    op.drop_column("import_batch", "processed_rows")
