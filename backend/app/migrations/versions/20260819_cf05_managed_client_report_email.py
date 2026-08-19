"""cf05: адрес и согласие клиента на получение отчёта (BIZ-51 срез-11).

Доп. №1 разд. 51.3, «отчёт клиенту». Additive: две колонки к существующей
таблице, данные не трогаются.

``report_opt_in`` заводится со значением «нет» у ВСЕХ накопленных строк — и это
правда: согласие никто не спрашивал, а молчание согласием не является.

Revision ID: 20260819_cf05_managed_client_report_email
Revises: 20260818_cf04_client_audit_report
Create Date: 2026-08-19
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260819_cf05_managed_client_report_email"
down_revision = "20260818_cf04_client_audit_report"
branch_labels = None
depends_on = None

_TABLE = "managed_client"


def upgrade() -> None:
    op.add_column(_TABLE, sa.Column("report_email", sa.String(length=320), nullable=True))
    # server_default обязателен: колонка NOT NULL, а строки в таблице уже есть.
    op.add_column(
        _TABLE,
        sa.Column(
            "report_opt_in",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column(_TABLE, "report_opt_in")
    op.drop_column(_TABLE, "report_email")
