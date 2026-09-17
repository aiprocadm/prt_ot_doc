"""cd02: выдача модуля «ГО и ЧС» существующим (Доп. №1 разд. 56.1).

Модуль ``civil_defense`` появился в каталоге продаваемых, а тариф «Всё
включено» по построению равен ВСЕМУ каталогу
(``PLANS["enterprise"].features = frozenset(FEATURE_CATALOG)``). Значит без
этой миграции у арендатора, купившего «Всё включено», набор перестал бы
совпадать с пресетом, и консоль показала бы ему «Свой набор» вместо тарифа —
подпись соврала бы про то, за что человек платит. Ровно этот же шаг делала
fs01, is02 и eco02 для предыдущих дисциплин.

**Кому включаем.** Тем, у кого включены ВСЕ двенадцать прежних продаваемых
модулей: это и есть «Всё включено», обещание тарифа обязано выполняться.

**Остальным пишем строку ВЫКЛЮЧЕНО.** Не пропускаем: «продаётся и выключено»
и «никогда не выдавалось» — разные состояния, и консоль обязана показывать
первое (правило BIZ-53 среза-1). Модуль по умолчанию закрыт — это и есть
default-OFF из BIZ-61.

Миграция идемпотентна: строка выдачи заводится только там, где её ещё нет.

Revision ID: 20260827_cd02_civil_defense_grant
Revises: 20260827_sec65_rls_cd
Create Date: 2026-08-27
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op

revision = "20260827_cd02_civil_defense_grant"
down_revision = "20260827_sec65_rls_cd"
branch_labels = None
depends_on = None

_CODE = "civil_defense"
_TITLE = "ГО и ЧС"

#: Снимок каталога ДО этой миграции. Список зафиксирован здесь намеренно, а не
#: импортирован из кода: миграция описывает состояние на свой момент, и правка
#: каталога в будущем не должна задним числом менять смысл уже выполненного
#: шага (тот же довод, что в fs01 и eco02).
_PREVIOUS_CATALOG = (
    "managed_clients",
    "committees",
    "contractors",
    "medical",
    "report_builder",
    "budget",
    "sout",
    "rules_engine",
    "warehouse",
    "fire_safety",
    "industrial_safety",
    "ecology",
)


def _tables(bind) -> set[str]:
    return set(sa.inspect(bind).get_table_names())


def upgrade() -> None:
    bind = op.get_bind()
    tables = _tables(bind)
    if not {"feature", "featureenablement"} <= tables:
        # Схема ещё не содержит контура выдачи (свежая база создаётся
        # метаданными) — выдавать нечего.
        return

    feature_id = bind.execute(
        sa.text("SELECT id FROM feature WHERE code = :code"), {"code": _CODE}
    ).scalar()
    if feature_id is None:
        feature_id = str(uuid.uuid4())
        bind.execute(
            sa.text(
                "INSERT INTO feature (id, code, title, created_at, updated_at, version) "
                "VALUES (:id, :code, :title, NOW(), NOW(), 1)"
            ),
            {"id": feature_id, "code": _CODE, "title": _TITLE},
        )

    granted = bind.execute(
        sa.text("SELECT tenant_id FROM featureenablement WHERE feature_id = :fid"),
        {"fid": feature_id},
    ).scalars()
    already = {str(row) for row in granted}

    rows = bind.execute(
        sa.text(
            "SELECT fe.tenant_id, f.code FROM featureenablement fe "
            "JOIN feature f ON f.id = fe.feature_id "
            "WHERE fe.on = true"
        )
    ).all()
    enabled: dict[str, set[str]] = {}
    for tenant_id, code in rows:
        enabled.setdefault(str(tenant_id), set()).add(str(code))

    known = bind.execute(sa.text("SELECT DISTINCT tenant_id FROM featureenablement")).scalars()

    previous = set(_PREVIOUS_CATALOG)
    for tenant_id in {str(row) for row in known} - already:
        turn_on = previous <= enabled.get(tenant_id, set())
        bind.execute(
            sa.text(
                "INSERT INTO featureenablement "
                '(id, tenant_id, feature_id, "on", config_json, created_at, updated_at, version) '
                "VALUES (:id, :tenant_id, :fid, :on, '{}', NOW(), NOW(), 1)"
            ),
            {
                "id": str(uuid.uuid4()),
                "tenant_id": tenant_id,
                "fid": feature_id,
                "on": turn_on,
            },
        )


def downgrade() -> None:
    bind = op.get_bind()
    if not {"feature", "featureenablement"} <= _tables(bind):
        return
    feature_id = bind.execute(
        sa.text("SELECT id FROM feature WHERE code = :code"), {"code": _CODE}
    ).scalar()
    if feature_id is None:
        return
    bind.execute(
        sa.text("DELETE FROM featureenablement WHERE feature_id = :fid"),
        {"fid": feature_id},
    )
    bind.execute(sa.text("DELETE FROM feature WHERE id = :fid"), {"fid": feature_id})
