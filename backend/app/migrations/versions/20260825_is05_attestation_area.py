"""is05: область аттестации по промбезопасности (Доп. №1 разд. 54.2).

У ядровой ``attestation`` область жила в свободной строке ``name``: «Б.9»,
«Б9», «подъёмные сооружения» и «ПС» были четырьмя разными областями, и вопрос
«кто аттестован по Б.9» не имел ответа. Добавляем отдельную колонку под
закрытый справочник областей (``app.core.disciplines.ATTESTATION_AREA_TITLES``).

Колонка NULLABLE и БЕЗ FK — это важно:

* nullable, потому что у аттестаций других дисциплин области нет; обязательная
  колонка сломала бы существующие записи и объявила бы всякую аттестацию
  промбезовской;
* без FK и без backfill — чисто additive-шаг (expand, правило OPS-74 разд.
  74.2). Класс граблей wa02 (FK в add_column к существующей таблице) сюда не
  относится: справочник живёт в коде, а не таблицей.

Старые записи остаются как есть: их ``name`` не разбирается автоматически —
угадывать область по свободному тексту значило бы приписать записи
принадлежность, которой в данных нет.

Revision ID: 20260825_is05_attestation_area
Revises: 20260825_sec65_rls_opo_work
Create Date: 2026-08-25
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260825_is05_attestation_area"
down_revision = "20260825_sec65_rls_opo_work"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "attestation",
        sa.Column("area_code", sa.String(length=16), nullable=True),
    )
    op.create_index(
        "ix_attestation_area", "attestation", ["tenant_id", "area_code"]
    )


def downgrade() -> None:
    op.drop_index("ix_attestation_area", table_name="attestation")
    op.drop_column("attestation", "area_code")
