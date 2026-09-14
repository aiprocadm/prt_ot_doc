"""BIZ-52 (срез-189): собственный домен партнёра и его цены для клиентов.

Revision ID: 20260914_biz52_domains_and_prices
Revises: 20260914_sec68_portal_otp_phone
Create Date: 2026-09-14

Два остатка строки BIZ-52, оба выглядели «внешними», и оба имели код-часть.

**52.2 — домен.** DNS и сертификаты действительно снаружи. Но ВЛАДЕНИЕ доменом
обязано подтверждаться кодом: иначе партнёр заявляет чужой домен, и платформа
начинает отдавать под ним его бренд и его страницу входа. Подтверждение —
TXT-запись с одноразовым словом: это понимают все регистраторы, и домен не
обязан заранее куда-либо указывать. Уникальность домена ГЛОБАЛЬНАЯ: два
арендатора с одним доменом — спор о владении, а не две настройки.

**52.4 — цены.** Отчёт о выручке партнёра было не из чего считать: цену
партнёр назначает сам, а хранить её было негде. Отдельная таблица, а не поле в
подписке: цена платформы для партнёра и цена партнёра для клиента — разные
числа по разным договорам. Сумма в КОПЕЙКАХ: деньги в плавающей точке рано или
поздно дают расхождение на копейку, которое невозможно объяснить. У строки есть
срок действия, потому что отчёт за прошлый квартал обязан считаться по цене
того квартала.

Миграция добавляющая: две новые таблицы, существующие не трогаются.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260914_biz52_domains_and_prices"
down_revision: str | Sequence[str] | None = "20260914_sec68_portal_otp_phone"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tenant_domains",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), nullable=False, index=True),
        sa.Column("domain", sa.String(length=253), nullable=False),
        sa.Column("verification_token", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.UniqueConstraint("domain", name="uq_tenant_domains_domain"),
    )
    op.create_index("ix_tenant_domains_domain", "tenant_domains", ["domain"])

    op.create_table(
        "reseller_prices",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("reseller_tenant_id", sa.String(length=36), nullable=False),
        sa.Column("client_tenant_id", sa.String(length=36), nullable=False),
        sa.Column("amount_minor", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="RUB"),
        sa.Column("period", sa.String(length=16), nullable=False, server_default="month"),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("note", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["reseller_tenant_id"], ["tenant.id"]),
        sa.ForeignKeyConstraint(["client_tenant_id"], ["tenant.id"]),
    )
    op.create_index(
        "ix_reseller_prices_pair_from",
        "reseller_prices",
        ["reseller_tenant_id", "client_tenant_id", "valid_from"],
    )
    op.create_index("ix_reseller_prices_reseller", "reseller_prices", ["reseller_tenant_id"])
    op.create_index("ix_reseller_prices_client", "reseller_prices", ["client_tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_reseller_prices_client", table_name="reseller_prices")
    op.drop_index("ix_reseller_prices_reseller", table_name="reseller_prices")
    op.drop_index("ix_reseller_prices_pair_from", table_name="reseller_prices")
    op.drop_table("reseller_prices")
    op.drop_index("ix_tenant_domains_domain", table_name="tenant_domains")
    op.drop_table("tenant_domains")
