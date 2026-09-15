"""SEC-66 разд. 66.3: порядок при утечке персональных данных (срез-207).

Revision ID: 20260915_sec66_pdn_breach
Revises: 20260915_biz53_tenant_sso_config
Create Date: 2026-09-15

ЧТО НАШЛА СВЕРКА. Критерии приёмки 70.1 по ПДн выполнены (экспорт субъекта,
обезличивание, журнал доступа). Но поимённый разбор разд. 66 нашёл незакрытый
пункт 66.3: «Порядок при утечке: уведомление Роскомнадзора и субъектов **в
установленные сроки** — процедура incident response».

Этого не было ВООБЩЕ. Виды происшествий (``IncidentType``) — про охрану труда:
несчастный случай, микротравма, «почти случилось», опасное условие. Утечки
персональных данных среди них нет, и у организации не было ни места, где про неё
записать, ни срока, который кто-то считает.

СРОКИ НЕ ХРАНЯТСЯ В ТАБЛИЦЕ. 152-ФЗ даёт 24 часа на уведомление регулятора и 72
часа на результаты расследования — **от момента ОБНАРУЖЕНИЯ**. Записанный
числом срок разошёлся бы с законом при первой же правке даты обнаружения,
поэтому хранится только момент обнаружения, а сроки считаются при чтении
(``app/modules/privacy/breach.py``).

ТРИ ОТДЕЛЬНЫХ ФАКТА, А НЕ ОДНА ГАЛОЧКА: уведомить регулятора, сообщить
результаты расследования, уведомить людей. Закон требует всех трёх, и они
выполняются по-разному и в разное время; одна отметка на все означала бы, что
выполнив лёгкое, организация считает закрытым и трудное.

RLS ОБЯЗАТЕЛЕН: таблица арендаторская, и в строке — факт утечки у конкретной
организации с числом пострадавших. Чужая такая строка — это и репутация, и
основание для проверки.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "20260915_sec66_pdn_breach"
down_revision: str | None = "20260915_biz53_tenant_sso_config"
branch_labels: str | None = None
depends_on: str | None = None

TABLE = "pdn_breach"
POLICY = "tenant_isolation"
PREDICATE = (
    "current_setting('app.bypass_rls', true) = 'on' "
    "OR tenant_id = current_setting('app.current_tenant', true)"
)


def _policy_exists(bind) -> bool:
    row = bind.execute(
        sa.text("SELECT 1 FROM pg_policies WHERE tablename = :table AND policyname = :policy"),
        {"table": TABLE, "policy": POLICY},
    ).first()
    return row is not None


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"
    if TABLE not in sa.inspect(bind).get_table_names():
        op.create_table(
            TABLE,
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("tenant_id", sa.String(length=36), nullable=False),
            # Момент ОБНАРУЖЕНИЯ — от него закон считает сроки. Обязателен:
            # запись об утечке без него не имеет смысла, потому что нечего
            # отсчитывать.
            sa.Column("discovered_at", sa.DateTime(timezone=True), nullable=False),
            # Момент самой утечки — если удалось установить. Пусто законно.
            sa.Column("happened_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("summary", sa.String(length=512), nullable=False),
            sa.Column("affected_people", sa.Integer(), nullable=True),
            sa.Column("regulator_notified_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("findings_reported_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("subjects_notified_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("registered_by_user_id", sa.String(length=36), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(["registered_by_user_id"], ["user.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_pdn_breach_tenant_discovered", TABLE, ["tenant_id", "discovered_at"], unique=False
        )

    if not is_pg:
        return
    op.execute("SET LOCAL lock_timeout = '5s'")
    if _policy_exists(bind):
        return
    op.execute(f'ALTER TABLE "{TABLE}" ENABLE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE "{TABLE}" FORCE ROW LEVEL SECURITY')
    op.execute(
        f'CREATE POLICY "{POLICY}" ON "{TABLE}" '
        f"FOR ALL USING ({PREDICATE}) WITH CHECK ({PREDICATE})"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(f'DROP POLICY IF EXISTS "{POLICY}" ON "{TABLE}"')
    op.drop_index("ix_pdn_breach_tenant_discovered", table_name=TABLE)
    op.drop_table(TABLE)
