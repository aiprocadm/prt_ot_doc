"""BIZ-53 разд. 53.3: настройка единого входа у арендатора (срез-204).

Revision ID: 20260915_biz53_tenant_sso_config
Revises: 20260915_b18_npa_act_responsible
Create Date: 2026-09-15

ЗАЧЕМ. Разд. 53.3 требует для enterprise-аренды «SSO/SAML/LDAP». Задача P10-13
дорожной карты стояла «не начато»: сотрудник крупного заказчика заводил в
платформе ЕЩЁ ОДИН пароль, а служба безопасности заказчика не могла ни отозвать
доступ централизованно, ни потребовать своей двухфакторности.

СЕКРЕТА ПРИЛОЖЕНИЯ В ТАБЛИЦЕ НЕТ. Колонка ``client_secret_env`` хранит ИМЯ
переменной окружения, из которой секрет читается на месте. Секрет в таблице
пережил бы её резервную копию, выгрузку для отладки и любой запрос «покажите
строку»; имя переменной само по себе бесполезно.

RLS ОБЯЗАТЕЛЕН. Таблица арендаторская, и в строке — адреса корпоративного
каталога заказчика и список разрешённых почтовых доменов, то есть карта того,
кто и откуда входит.

Умолчание ``provider='disabled'``: появление таблицы ничего не меняет для
существующих развёртываний, пока настройку не заполнили.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "20260915_biz53_tenant_sso_config"
down_revision: str | None = "20260915_b18_npa_act_responsible"
branch_labels: str | None = None
depends_on: str | None = None

TABLE = "tenant_sso_config"
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
            sa.Column("provider", sa.String(length=16), nullable=False, server_default="disabled"),
            sa.Column("issuer", sa.String(length=512), nullable=False, server_default=""),
            sa.Column("client_id", sa.String(length=255), nullable=False, server_default=""),
            sa.Column(
                "client_secret_env", sa.String(length=128), nullable=False, server_default=""
            ),
            sa.Column(
                "authorization_endpoint", sa.String(length=512), nullable=False, server_default=""
            ),
            sa.Column("token_endpoint", sa.String(length=512), nullable=False, server_default=""),
            sa.Column("jwks_uri", sa.String(length=512), nullable=False, server_default=""),
            sa.Column("email_domains", sa.JSON(), nullable=False),
            sa.Column("jit_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column(
                "default_role", sa.String(length=64), nullable=False, server_default="worker"
            ),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            # Одна настройка на арендатора: две строки означали бы два ответа на
            # вопрос «через кого пускаем», и какой из них настоящий — неизвестно.
            sa.UniqueConstraint("tenant_id", name="uq_tenant_sso_config_tenant"),
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
    op.drop_table(TABLE)
