"""SEC-68 (срез-186): второй канал доставки одноразового кода — телефон.

Revision ID: 20260914_sec68_portal_otp_phone
Revises: 20260911_b18_compliance_requirements
Create Date: 2026-09-14

Разд. 68.1 требует привязки ссылки к получателю. Привязка была, но канал был
ровно один — почта, и строка матрицы держала в остатке «SMS как второй канал —
внешний поставщик, вне кода».

Поставщика SMS действительно выбирает владелец. Но место для телефона и выбор
канала — это код, и без них подключение поставщика оставалось бы разработкой.

Колонка ОТДЕЛЬНАЯ, а не расширенное значение ``otp_email``: адрес и телефон —
разные вещи, и колонка с именем «email», хранящая телефон, врала бы каждому,
кто её читает. Заполнена ровно одна из двух; какая — тот канал и используется.

Миграция добавляющая (expand): NULL означает «привязки по телефону нет», то есть
поведение всех ранее выданных ссылок. Бэкфилл не нужен.

Таблица уже armed RLS (SEC-65) — ``ADD COLUMN`` политики не трогает.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260914_sec68_portal_otp_phone"
down_revision: str | Sequence[str] | None = "20260911_b18_compliance_requirements"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "client_portal_tokens",
        sa.Column("otp_phone", sa.String(length=32), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("client_portal_tokens", "otp_phone")
