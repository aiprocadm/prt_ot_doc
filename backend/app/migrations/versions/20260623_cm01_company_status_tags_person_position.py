"""cm01: company.status/tags + person.position_title (additive).

Поля, которые фронт собирал, но бэкенд не принимал (тихая потеря данных):
- company.status (CRM-статус карточки) — VARCHAR NOT NULL server_default 'active'
  (бэкфилл существующих строк; VARCHAR, не PG-enum — снимает класс enum-parity).
- company.tags (свободные метки) — JSON nullable (без server_default на JSON,
  чтобы add_column на существующую таблицу не падал на PG).
- person.position_title — свободнотекстовая должность; имя `position` занято
  relationship на каталог Position, поэтому отдельная колонка.

Имена таблиц ЛИТЕРАЛОМ (AST-audit blindspot). Honest downgrade удаляет колонки
в обратном порядке.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260623_cm01_company_status_tags_person_position"
down_revision = "20260621_wp06_work_permit_type_specific"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "company",
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
    )
    op.add_column("company", sa.Column("tags", sa.JSON(), nullable=True))
    op.add_column("person", sa.Column("position_title", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("person", "position_title")
    op.drop_column("company", "tags")
    op.drop_column("company", "status")
