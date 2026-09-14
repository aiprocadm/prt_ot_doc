"""OPS-73 (срез-191): версия схемы вебхука живёт у ПОДПИСЧИКА.

Revision ID: 20260914_ops73_endpoint_schema_version
Revises: 20260914_biz52_domains_and_prices
Create Date: 2026-09-14

Остаток строки: «унификация конвертов и единиц подписи через bump schema_version
(v2)». Унифицировать разом нельзя — это ломающее изменение для всех живых
подписчиков сразу. Поэтому версия становится свойством ПОДПИСЧИКА: платформа
шлёт каждому по той схеме, к которой он готов.

NULL = умолчание развёртывания (сейчас «1»), то есть поведение всех уже
заведённых подписчиков не меняется. Ровно это и требует разд. 73.2: старая
схема продолжает работать, пока её кто-то использует.

Миграция добавляющая.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260914_ops73_endpoint_schema_version"
down_revision: str | Sequence[str] | None = "20260914_biz52_domains_and_prices"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "webhook_endpoints",
        sa.Column("schema_version", sa.String(length=8), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("webhook_endpoints", "schema_version")
