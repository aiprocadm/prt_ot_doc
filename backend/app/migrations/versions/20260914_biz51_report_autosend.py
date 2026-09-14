"""BIZ-51 (срез-193): автоматическая рассылка отчёта клиенту — только на подтверждённые адреса.

Revision ID: 20260914_biz51_report_autosend
Revises: 20260914_ops71_saved_import_profiles
Create Date: 2026-09-14

Срез-11 завёл адрес и согласие, но автоматику включать НЕ СТАЛ — с доводом
«сперва обкатать вручную, иначе первая же ошибка адреса уедет всем разом».
Довод верный, и снимается он не отменой, а условием.

``report_verified_at`` — когда на этот адрес отчёт ДОШЁЛ (а не «когда
отправили»). Автоматическая рассылка идёт только на адреса с этой отметкой:
адрес, на который письмо уже приходило, ошибочным быть не может. Смена адреса
обнуляет отметку — новый адрес снова непроверенный.

``report_last_auto_sent_at`` — чтобы не слать дважды за один период.

Миграция добавляющая: у всех накопленных клиентов обе отметки пусты, то есть
автоматическая рассылка им не пойдёт, пока отчёт не уйдёт вручную хотя бы раз.
Это и есть «обкатать вручную», записанное правилом вместо обещания.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260914_biz51_report_autosend"
down_revision: str | Sequence[str] | None = "20260914_ops71_saved_import_profiles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "managed_client"


def upgrade() -> None:
    op.add_column(
        _TABLE, sa.Column("report_verified_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        _TABLE,
        sa.Column("report_last_auto_sent_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column(_TABLE, "report_last_auto_sent_at")
    op.drop_column(_TABLE, "report_verified_at")
