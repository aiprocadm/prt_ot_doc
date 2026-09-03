"""in01: дисциплина происшествия (Доп. №1 разд. 54.2 + кросс-контур).

До этой колонки инцидент на ОПО был НЕОТЛИЧИМ от микротравмы в офисе: у
``incident`` есть вид, тяжесть, площадка и стадия расследования, но нет
отнесения к дисциплине. Разд. 54.2 требует связь промбеза с «расследованиями
инцидентов на ОПО», а отчёт в Ростехнадзор спрашивает число инцидентов — и
четыре комплекта отчётности подряд честно писали: «аварии не подсказываются,
реестр происшествий не размечен дисциплиной».

Дыра КРОСС-ДИСЦИПЛИНАРНАЯ: ровно так же неотличимы разлив топлива
(экология), пожар (ПБ) и ЧС на объекте (ГО и ЧС) — поэтому размечается само
происшествие, а контуры дисциплин показывают свою часть. Приём тот же, что у
курса обучения (cd06) и стажировки (tr06): общая сущность + колонка
``discipline``.

Колонка NULLABLE: пусто означает «не размечено», а НЕ «охрана труда».
Backfill НЕ делается намеренно — приписать существующим происшествиям
дисциплину по виду или названию значило бы выдумать данные, которых нет.

Additive-шаг (expand, правило OPS-74 разд. 74.2 по построению).

Revision ID: 20260903_in01_incident_discipline
Revises: 20260901_sec65_rls_violations
Create Date: 2026-09-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260903_in01_incident_discipline"
down_revision = "20260901_sec65_rls_violations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "incident",
        sa.Column("discipline", sa.String(length=32), nullable=True),
    )
    op.create_index(
        "ix_incident_discipline",
        "incident",
        ["tenant_id", "discipline"],
    )


def downgrade() -> None:
    op.drop_index("ix_incident_discipline", table_name="incident")
    op.drop_column("incident", "discipline")
