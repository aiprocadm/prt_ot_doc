"""BIZ-52 срез-1: вид арендатора `reseller` (Доп. №1 разд. 52.1).

Уровень арендатора в иерархии продажи платформы хранится в `tenant.kind`.
Значение добавляется В ТИП, существующие строки не трогаются: ни одна из них не
меняет смысл — все они как были клиентами платформы, так и остаются (разд. 3
плана, «Non-Destructive Upgrade Principle»).

Revision ID: 20260811_rs01_tenant_kind_reseller
Revises: 20260808_biz61_module_trial
Create Date: 2026-08-11
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260811_rs01_tenant_kind_reseller"
down_revision = "20260808_biz61_module_trial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # PG запрещает пользоваться новым значением в той же транзакции, где оно
        # добавлено, поэтому расширение типа коммитится отдельно.
        # IF NOT EXISTS — чтобы повторный прогон не падал.
        with op.get_context().autocommit_block():
            op.execute("ALTER TYPE tenantkind ADD VALUE IF NOT EXISTS 'reseller'")
    # SQLite хранит Enum как VARCHAR с CHECK, а тестовая схема собирается из
    # метаданных модели — новое значение там появляется само.


def downgrade() -> None:
    # Значение PG-перечисления нельзя убрать, не пересоздав тип целиком: строки
    # с этим значением уже могут существовать, и откат превратился бы в потерю
    # арендаторов. Обратный шаг намеренно пустой.
    pass
