"""SEC-68: лимит использований magic link клиентского портала (разд. 68.1).

Revision ID: 20260728_sec68_portal_token_usage
Revises: 20260728_sec66_pdn_registry_dpa
Create Date: 2026-07-28

Разд. 68.1 против угрозы «пересылка ссылки третьему лицу» и «бессрочный доступ»
требует одноразовости там, где она возможна. Три колонки на ``client_portal_tokens``:

  * ``max_uses``     — NULL = без ограничения (текущее поведение всех выданных
    ссылок, поэтому бэкфилл не нужен), 1 = строго одноразовая;
  * ``uses_count``   — растёт при каждой успешной проверке токена, так что
    пересланная копия исчерпывает тот же лимит, что и оригинал;
  * ``last_used_at`` — когда ссылкой пользовались в последний раз; без этого на
    вопрос «ходили ли по ней после увольнения подрядчика» ответить нечем.

Таблица уже armed RLS (SEC-65) — ``ALTER TABLE ... ADD COLUMN`` политики не трогает,
поэтому реестр не меняется.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260728_sec68_portal_token_usage"
down_revision: str | Sequence[str] | None = "20260728_sec66_pdn_registry_dpa"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("client_portal_tokens", sa.Column("max_uses", sa.Integer(), nullable=True))
    op.add_column(
        "client_portal_tokens",
        sa.Column("uses_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "client_portal_tokens",
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("client_portal_tokens", "last_used_at")
    op.drop_column("client_portal_tokens", "uses_count")
    op.drop_column("client_portal_tokens", "max_uses")
