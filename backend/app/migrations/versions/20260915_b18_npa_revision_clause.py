"""B.18 разд. 19.4: у редакции акта появился текст (срез-202).

Revision ID: 20260915_b18_npa_revision_clause
Revises: 20260915_b18_npa_act_owner
Create Date: 2026-09-15

ЗАЧЕМ. Разд. 19.4 требует процесс «черновик → публикация → ДИФФ → уведомления
→ задачи на пересмотр → контроль завершения». Всё, кроме диффа, уже работало
(срезы 141, 144, 198). Дифф был невозможен по построению: ``npa_revision``
хранил только ``change_summary`` — одну фразу вроде «Обновлены программы
обучения», — а пункты принадлежали акту. Система знала, ЧТО редакция есть, и не
знала, чем она отличается от предыдущей.

ЧТО ДЕЛАЕТ. Заводит ``npa_revision_clause`` — снимок текста пунктов на момент
редакции. Ничего существующего не трогает: ни колонок, ни ограничений, ни
данных. Фаза expand в чистом виде, откат сносит только новую таблицу.

ПОЧЕМУ ОТДЕЛЬНАЯ ТАБЛИЦА, А НЕ ``revision_id`` У ``npa_clause``. На
``npa_clause.id`` ссылается ``ComplianceRequirement.clause_id`` настоящим
внешним ключом (миграция ``20260911_b18_compliance_requirements``). Пункт там —
ЛИЧНОСТЬ: требование «проводить обучение по п. 4» обязано указывать на п. 4
независимо от того, сколько редакций акт пережил. Раздав пункты по редакциям,
мы привязали бы каждое требование к одной редакции, и при следующей оно стало
бы ссылаться в никуда.

RLS НЕ ДОБАВЛЯЕТСЯ, и это не забывчивость. Таблица наследует область у
``npa_revision`` → ``npa_act``: там нет ``tenant_id``, и политика
``tenant_isolation`` (разд. 65) к ней неприложима — текст федерального акта
обязан быть виден всем. Видимость держится единственным фильтром
``app/domains/npa/scope.py`` (срез-201) и сторожем над ним; сюда добираются
только через уже проверенный акт.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "20260915_b18_npa_revision_clause"
down_revision: str | None = "20260915_b18_npa_act_owner"
branch_labels: str | None = None
depends_on: str | None = None

TABLE = "npa_revision_clause"


def upgrade() -> None:
    if TABLE in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        TABLE,
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("revision_id", sa.String(), nullable=False),
        sa.Column("code", sa.String(length=128), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["revision_id"], ["npa_revision.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        # Один код — один пункт внутри редакции. Без этого «п. 4» мог бы
        # встретиться в снимке дважды, и дифф, сопоставляющий пункты ПО КОДУ,
        # молча взял бы любой из них.
        sa.UniqueConstraint("revision_id", "code", name="uq_npa_revision_clause_code"),
    )
    op.create_index(
        op.f("ix_npa_revision_clause_revision_id"), TABLE, ["revision_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_npa_revision_clause_revision_id"), table_name=TABLE)
    op.drop_table(TABLE)
