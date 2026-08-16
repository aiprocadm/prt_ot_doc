"""cf02: откуда узнали об изменении (BIZ-51 срез-2).

Доп. №1 разд. 51.2: сигналы приходят не только от человека, но и из импорта.
Additive: две колонки к существующей таблице, данные не трогаются.

``source`` заполняется значением ``manual`` у всех уже накопленных записей —
и это правда: до этого среза другого источника не существовало.

Revision ID: 20260816_cf02_client_change_source
Revises: 20260816_cf01_client_change
Create Date: 2026-08-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260816_cf02_client_change_source"
down_revision = "20260816_cf01_client_change"
branch_labels = None
depends_on = None

_TABLE = "client_change"
_INDEX = "ix_client_change_source_ref"


def upgrade() -> None:
    # server_default обязателен: колонка NOT NULL, а строки в таблице уже есть.
    op.add_column(
        _TABLE,
        sa.Column("source", sa.String(length=16), nullable=False, server_default="manual"),
    )
    op.add_column(_TABLE, sa.Column("source_ref", sa.String(length=36), nullable=True))
    # Индекс нужен не для показа ленты, а для вопроса «эту партию уже
    # разбирали?»: без него повторный разбор перебирал бы всю ленту арендатора.
    op.create_index(_INDEX, _TABLE, ["tenant_id", "source_ref"])


def downgrade() -> None:
    op.drop_index(_INDEX, table_name=_TABLE)
    op.drop_column(_TABLE, "source_ref")
    op.drop_column(_TABLE, "source")
