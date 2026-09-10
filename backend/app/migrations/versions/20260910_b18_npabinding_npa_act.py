"""B.18 (разд. 19.3): связи НПА ведут в общий реестр актов, а не в пустую таблицу.

Revision ID: 20260910_b18_npabinding_npa_act
Revises: 20260908_sec68_portal_otp
Create Date: 2026-09-10

С начальной схемы ``npabinding.npa_id`` ссылался на арендаторскую таблицу
``npa`` (контур risk_register), а оценка влияния (``NpaImpactService``) искала
связи по ``npa_act.id`` — общему реестру, который ведёт владелец платформы
(срез-141). Расхождение не стреляло только потому, что связей не заводил
никто: таблица пуста у всех арендаторов. Срез-142 даёт связям точку входа
(``POST /npa/{act_id}/bindings``), и ключ обязан указывать туда, где акты
на самом деле живут.

Что делает:

  * удаляет строки, чей ``npa_id`` не найден в ``npa_act`` (таких быть не
    должно — писать в таблицу было нечем; если есть, это ручной мусор, а не
    данные: они не видны ни одному экрану);
  * переводит внешний ключ ``npa_id`` с ``npa.id`` на ``npa_act.id``. Имя
    старого ключа не задавалось при создании, поэтому берётся из каталога;
  * добавляет уникальность ``(tenant_id, npa_id, entity_type, entity_id)`` —
    одна и та же связь дважды бессмысленна, а гонку двух заявок ручка ловит
    именно этим индексом (как ``POST /npa`` — уникальностью кода акта).

Таблица ``npa`` остаётся в базе без модели (``RLS_MODEL_LESS_TABLES``): снос
данных — решение владельца, список — ``docs/CLEANUP_CANDIDATES.md``.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260910_b18_npabinding_npa_act"
down_revision: str | Sequence[str] | None = "20260908_sec68_portal_otp"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "npabinding"
NEW_FK = "fk_npabinding_npa_id_npa_act"
UNIQUE = "uq_npabinding_target"


def _fk_name_on_npa_id() -> str | None:
    inspector = sa.inspect(op.get_bind())
    for fk in inspector.get_foreign_keys(TABLE):
        if fk.get("constrained_columns") == ["npa_id"]:
            return fk.get("name")
    return None


def upgrade() -> None:
    op.execute(f"DELETE FROM {TABLE} WHERE npa_id NOT IN (SELECT id FROM npa_act)")
    old_fk = _fk_name_on_npa_id()
    if old_fk:
        op.drop_constraint(old_fk, TABLE, type_="foreignkey")
    op.create_foreign_key(NEW_FK, TABLE, "npa_act", ["npa_id"], ["id"])
    op.create_unique_constraint(UNIQUE, TABLE, ["tenant_id", "npa_id", "entity_type", "entity_id"])


def downgrade() -> None:
    op.drop_constraint(UNIQUE, TABLE, type_="unique")
    op.drop_constraint(NEW_FK, TABLE, type_="foreignkey")
    op.execute(f"DELETE FROM {TABLE} WHERE npa_id NOT IN (SELECT id FROM npa)")
    op.create_foreign_key("npabinding_npa_id_fkey", TABLE, "npa", ["npa_id"], ["id"])
