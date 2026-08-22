"""gc01: группа компаний — parent_company_id у Company (BIZ-53 разд. 53.3).

Доп. №1 разд. 53.3: «Группа компаний / филиальная иерархия внутри одного
enterprise-tenant». Нижние уровни иерархии (Company → Branch → Site) уже
существуют (RC-014); верхнего — связи «головная компания → дочерние» — не было
вовсе, хотя docstring модели Branch этот уровень обещает.

Колонка — app-level reference БЕЗ DB FK: ``add_column`` с FK на существующую
таблицу — класс миграционных граблей wa02 (прецедент ``site.branch_id``).
Целостность (существование родителя, запрет самоссылки и циклов, запрет
архивирования при активных дочках) обеспечивает API-слой.

Чисто additive-шаг (expand): nullable-колонка + индекс, старый код её не
замечает — правило OPS-74 разд. 74.2 соблюдено по построению.

Revision ID: 20260822_gc01_company_parent_id
Revises: 20260819_fs01_fire_safety_module_grant
Create Date: 2026-08-22
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260822_gc01_company_parent_id"
down_revision = "20260819_fs01_fire_safety_module_grant"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("company", sa.Column("parent_company_id", sa.String(length=36), nullable=True))
    op.create_index(
        "ix_company_parent_company_id", "company", ["parent_company_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_company_parent_company_id", table_name="company")
    op.drop_column("company", "parent_company_id")
