"""cf03: личность находки Data Quality не влезает в 36 знаков (BIZ-51 срез-3).

Разд. 51.2 называет Data Quality третьим источником сигналов ленты. Личность
находки там составная — ``dq:<сущность>:<id записи>:<дата истечения>`` (дата
внутри неспроста: продлённая и снова просроченная запись обязана дать новый
сигнал, а не утонуть в дедупликации). Такой ref длиннее 36 знаков, под которые
колонка была скроена в cf02 ради id партии импорта.

Только расширение типа: данные не трогаются, индекс остаётся тем же.
``batch_alter_table`` — ради SQLite (dev-база не умеет ALTER COLUMN TYPE).

Revision ID: 20260817_cf03_client_change_source_ref_width
Revises: 20260816_cf02_client_change_source
Create Date: 2026-08-17
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260817_cf03_client_change_source_ref_width"
down_revision = "20260816_cf02_client_change_source"
branch_labels = None
depends_on = None

_TABLE = "client_change"


def upgrade() -> None:
    with op.batch_alter_table(_TABLE) as batch_op:
        batch_op.alter_column(
            "source_ref",
            existing_type=sa.String(length=36),
            type_=sa.String(length=128),
            existing_nullable=True,
        )


def downgrade() -> None:
    # Обратное сужение возможно, пока в колонке нет длинных значений; при
    # накопленных находках Data Quality откат обязан упасть, а не обрезать их.
    with op.batch_alter_table(_TABLE) as batch_op:
        batch_op.alter_column(
            "source_ref",
            existing_type=sa.String(length=128),
            type_=sa.String(length=36),
            existing_nullable=True,
        )
