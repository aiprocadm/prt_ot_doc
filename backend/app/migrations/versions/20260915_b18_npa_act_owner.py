"""B.18 разд. 19.1: у нормативного акта появился владелец (срез-201).

Revision ID: 20260915_b18_npa_act_owner
Revises: 20260914_sec65_rls_domains_and_profiles
Create Date: 2026-09-15

ЗАЧЕМ. Реестр ``npa_act`` знал только федеральные акты, которые заводит
владелец платформы. Собственный приказ организации («О назначении
ответственного за электрохозяйство») записать было некуда, и вся обвязка —
редакции, пункты, связи с документами, требования, оценка влияния — для таких
актов не работала вовсе.

ЧТО ДЕЛАЕТ. Добавляет ``owner_tenant_id``: NULL — общий реестр (как было),
иначе — акт этого арендатора. Колонка nullable, старые строки становятся
общими автоматически, читатели без неё продолжают работать — фаза expand.

ГЛАВНОЕ ЗДЕСЬ — ЗАМЕНА УНИКАЛЬНОСТИ, а не новая колонка.

Было ``UNIQUE(code)`` на всю таблицу. Оставить его — значит отдать «Приказ №1»
первому арендатору, который успел, а всем остальным вечно отвечать 409 про акт,
которого они даже не видят.

Заменить на обычный ``UNIQUE(owner_tenant_id, code)`` НЕЛЬЗЯ: и PostgreSQL, и
SQLite считают NULL не равным самому себе, поэтому два федеральных акта с одним
кодом (у обоих ``owner_tenant_id IS NULL``) такой индекс пропустит — и защита,
которая была в реестре с первого дня, тихо исчезнет.

Поэтому случая два, и у каждого свой ЧАСТИЧНЫЙ уникальный индекс:

* ``uq_npa_act_registry_code`` — UNIQUE(code) WHERE owner_tenant_id IS NULL;
* ``uq_npa_act_owner_code`` — UNIQUE(owner_tenant_id, code) WHERE owner_tenant_id IS NOT NULL.

RLS К ЭТОЙ ТАБЛИЦЕ НЕ ПРИМЕНЯЕТСЯ И ЗДЕСЬ НЕ ДОБАВЛЯЕТСЯ. ``npa_act`` — общая
таблица вне схемы арендатора: у неё нет ``tenant_id``, и политика
``tenant_isolation`` (разд. 65) к ней неприложима — строка с NULL должна быть
видна ВСЕМ. Цена названа честно: единственный рубеж видимости здесь — условие в
запросе, собранное в ``app/domains/npa/scope.py``, и сторож
``tests/test_npa_scope_guard.py``, который запрещает спрашивать акты мимо него.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "20260915_b18_npa_act_owner"
down_revision: str | None = "20260914_sec65_rls_domains_and_profiles"
branch_labels: str | None = None
depends_on: str | None = None

TABLE = "npa_act"
COLUMN = "owner_tenant_id"
REGISTRY_INDEX = "uq_npa_act_registry_code"
OWNER_INDEX = "uq_npa_act_owner_code"


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {col["name"] for col in inspector.get_columns(TABLE)}
    if COLUMN not in columns:
        op.add_column(TABLE, sa.Column(COLUMN, sa.String(length=36), nullable=True))

    if _is_postgres():
        # Имя ограничения PostgreSQL дал сам (таблица создана с безымянным
        # UniqueConstraint("code")), поэтому ищем его по составу, а не по
        # угаданному имени: на базах, переживших ручные правки, оно другое.
        for constraint in inspector.get_unique_constraints(TABLE):
            if list(constraint["column_names"]) == ["code"]:
                op.drop_constraint(constraint["name"], TABLE, type_="unique")
        # Уникальность могли оформить и индексом, а не ограничением.
        for index in inspector.get_indexes(TABLE):
            if index.get("unique") and list(index["column_names"]) == ["code"]:
                op.drop_index(index["name"], table_name=TABLE)

    existing = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(TABLE)}
    if REGISTRY_INDEX not in existing:
        op.create_index(
            REGISTRY_INDEX,
            TABLE,
            ["code"],
            unique=True,
            postgresql_where=sa.text(f"{COLUMN} IS NULL"),
            sqlite_where=sa.text(f"{COLUMN} IS NULL"),
        )
    if OWNER_INDEX not in existing:
        op.create_index(
            OWNER_INDEX,
            TABLE,
            [COLUMN, "code"],
            unique=True,
            postgresql_where=sa.text(f"{COLUMN} IS NOT NULL"),
            sqlite_where=sa.text(f"{COLUMN} IS NOT NULL"),
        )


def downgrade() -> None:
    """Откат СНОСИТ локальные акты арендаторов — иначе он невозможен.

    Возврат к ``UNIQUE(code)`` требует, чтобы код был уникален на всю таблицу,
    а локальные акты заводились именно с повторяющимися кодами. Молча выбрать,
    какой «Приказ №1» оставить, нельзя; поэтому откат удаляет все строки с
    владельцем и всё, что на них ссылалось каскадом внешних ключей. Это
    сознательно громкое действие, а не тихая потеря.
    """

    op.execute(sa.text(f"DELETE FROM {TABLE} WHERE {COLUMN} IS NOT NULL"))
    existing = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(TABLE)}
    if OWNER_INDEX in existing:
        op.drop_index(OWNER_INDEX, table_name=TABLE)
    if REGISTRY_INDEX in existing:
        op.drop_index(REGISTRY_INDEX, table_name=TABLE)
    if _is_postgres():
        op.create_unique_constraint("npa_act_code_key", TABLE, ["code"])
    op.drop_column(TABLE, COLUMN)
