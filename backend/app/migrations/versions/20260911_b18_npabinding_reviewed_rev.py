"""B.18 (разд. 19.4): связь НПА помнит, по какой редакции её сверяли.

Revision ID: 20260911_b18_npabinding_reviewed_rev
Revises: 20260910_b18_npabinding_npa_act
Create Date: 2026-09-11

Новая редакция акта попадала в общий реестр молча: арендатор с привязанными
документами узнавал о ней только если сам заходил на экран НПА. Столбец
``npabinding.reviewed_revision_id`` — редакция, по которой цель связи сверяли
в последний раз. Пока она совпадает с действующей — связь актуальна; вышла
новая — связь «не пересмотрена», и это видно в Центре внимания и в задачах
актуализации. Ставится при создании связи и ручкой «Пересмотрено».

Столбец nullable и без внешнего ключа: старые связи получают NULL («ни по
какой редакции не сверяли») и при действующей редакции считаются
непересмотренными — честнее, чем объявить их проверенными задним числом.
Ссылка в shared-таблицу ``npa_revision`` не оформляется ключом по той же
причине, что ``npa_id`` в ORM: настоящую целостность здесь держит логика
ручки, а редакции из реестра не удаляются.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260911_b18_npabinding_reviewed_rev"
down_revision: str | Sequence[str] | None = "20260910_b18_npabinding_npa_act"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "npabinding",
        sa.Column("reviewed_revision_id", sa.String(length=36), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("npabinding", "reviewed_revision_id")
