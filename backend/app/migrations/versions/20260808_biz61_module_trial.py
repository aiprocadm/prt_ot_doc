"""biz61: срок действия выдачи модуля — временный доступ (Доп. №2, разд. 61.2).

ТЗ называет три источника включения модуля: редакция тарифа, индивидуальная
надбавка и **временный доступ (trial на N дней)**. Третьего не было: выдача
знала только «включено/выключено», и «дать посмотреть на две недели» означало
поставить напоминание человеку — а человек забывает, и модуль остаётся
открытым бесплатно.

Additive: колонка nullable, NULL = бессрочная выдача (всё, что выдано до сих
пор). RLS у таблицы уже вооружён — новых политик не требуется.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260808_biz61_module_trial"
down_revision = "20260808_mc05_managed_client_transfer"
branch_labels = None
depends_on = None

_TABLE = "featureenablement"
_COLUMN = "expires_at"


def upgrade() -> None:
    op.add_column(
        _TABLE,
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Индекс по сроку: отчёт «какие пробные доступы истекают» не должен читать
    # всю таблицу выдач платформы.
    op.create_index(
        "ix_feature_enablement_expires_at",
        _TABLE,
        ["expires_at"],
        postgresql_where=sa.text("expires_at IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_feature_enablement_expires_at", table_name=_TABLE)
    op.drop_column(_TABLE, _COLUMN)
