"""B.18 разд. 19.1 «owner»: ответственный арендатора за акт (срез-203).

Revision ID: 20260915_b18_npa_act_responsible
Revises: 20260915_b18_npa_revision_clause
Create Date: 2026-09-15

ЗАЧЕМ. Поимённая сверка разд. 19 показала: из восьми пунктов 19.1 семь закрыты
(федеральные акты, локальные акты, редакции, даты вступления, даты отмены,
ссылки на процессы и сущности, статус актуальности), а восьмой — **owner** —
нет. Прошлая волна читала owner как «чей акт» и считала его закрытым вместе с
federal/local. Это прочтение не выдерживает проверки: «федеральные НПА» и
«локальные НПА» — уже два отдельных пункта того же списка, третий пункт про то
же был бы повтором; а разд. 19.2 рядом пишет «responsible owner» про человека.

ПОЧЕМУ ОТДЕЛЬНАЯ АРЕНДАТОРСКАЯ ТАБЛИЦА, А НЕ КОЛОНКА У ``npa_act``. Один приказ
Минтруда действует на всех арендаторов, и ведут его в каждой организации РАЗНЫЕ
люди. Колонка у общей строки дала бы одного ответственного на всю платформу —
ответ, верный максимум для одного арендатора.

RLS ЗДЕСЬ ОБЯЗАТЕЛЕН, в отличие от соседних таблиц НПА. У ``npa_act``,
``npa_revision`` и ``npa_revision_clause`` нет ``tenant_id``, и политика
``tenant_isolation`` к ним неприложима. У этой таблица ``tenant_id`` ЕСТЬ, и
в ней лежит связка «человек ↔ акт»: чужая такая связка рассказывает, чем
занимается чужая организация и кто у неё за это отвечает.

Внешний ключ ``npa_id`` → ``npa_act.id`` ставится ЗДЕСЬ, а не в ORM: ключ из
tenant-базы в shared-базу ломает ``create_all`` (прецеденты ``NPABinding.npa_id``
и ``ComplianceRequirement.npa_id``).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "20260915_b18_npa_act_responsible"
down_revision: str | None = "20260915_b18_npa_revision_clause"
branch_labels: str | None = None
depends_on: str | None = None

TABLE = "npa_act_responsible"
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
            sa.Column("npa_id", sa.String(length=36), nullable=False),
            sa.Column("owner_user_id", sa.String(length=36), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(["owner_user_id"], ["user.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            # Один ответственный на пару «арендатор + акт». Без этого у акта
            # завелись бы два ответственных, и вопрос «к кому идёт задача
            # актуализации» снова стал бы без ответа.
            sa.UniqueConstraint("tenant_id", "npa_id", name="uq_npa_act_responsible"),
        )
        op.create_index(op.f("ix_npa_act_responsible_npa_id"), TABLE, ["npa_id"], unique=False)
        op.create_index(
            op.f("ix_npa_act_responsible_owner_user_id"), TABLE, ["owner_user_id"], unique=False
        )
        if is_pg:
            op.create_foreign_key(
                "fk_npa_act_responsible_npa_id", TABLE, "npa_act", ["npa_id"], ["id"]
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
    op.drop_index(op.f("ix_npa_act_responsible_owner_user_id"), table_name=TABLE)
    op.drop_index(op.f("ix_npa_act_responsible_npa_id"), table_name=TABLE)
    op.drop_table(TABLE)
