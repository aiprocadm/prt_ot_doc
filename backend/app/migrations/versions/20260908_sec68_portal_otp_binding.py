"""SEC-68: привязка magic link к получателю через одноразовый код (разд. 68.1).

Revision ID: 20260908_sec68_portal_otp
Revises: 20260905_eco08_reporting_deadline
Create Date: 2026-09-08

Модель угроз (docs/security/EXTERNAL_PERIMETER.md) держала одну строку красной:
пересланная третьему лицу ссылка. Одноразовость помогает лишь отчасти — кто
первым откроет, тот и войдёт. Разд. 68.1 предлагает привязку к получателю, и
здесь она появляется.

Четыре колонки на ``client_portal_tokens``:

  * ``otp_email``      — адрес, на который уходит код. NULL = привязки нет
    (поведение всех ранее выданных ссылок, бэкфилл не нужен);
  * ``otp_code_hash``  — код хранится ХЕШЕМ, как и сам токен: утечка базы не
    должна давать вход;
  * ``otp_expires_at`` — код живёт минуты, а не сутки: он ходит по почте, а
    почта хранится дольше, чем нужно;
  * ``otp_attempts``   — счётчик неверных попыток. Шестизначный код без
    счётчика перебирается за минуты.

Таблица уже armed RLS (SEC-65) — ``ALTER TABLE ... ADD COLUMN`` политики не
трогает, поэтому реестр не меняется.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260908_sec68_portal_otp"
down_revision: str | Sequence[str] | None = "20260905_eco08_reporting_deadline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "client_portal_tokens", sa.Column("otp_email", sa.String(length=320), nullable=True)
    )
    op.add_column(
        "client_portal_tokens", sa.Column("otp_code_hash", sa.String(length=128), nullable=True)
    )
    op.add_column(
        "client_portal_tokens",
        sa.Column("otp_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "client_portal_tokens",
        sa.Column("otp_attempts", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("client_portal_tokens", "otp_attempts")
    op.drop_column("client_portal_tokens", "otp_expires_at")
    op.drop_column("client_portal_tokens", "otp_code_hash")
    op.drop_column("client_portal_tokens", "otp_email")
