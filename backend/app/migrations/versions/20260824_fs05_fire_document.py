"""fs05: учётные карточки документов ПБ (Доп. №1 разд. 54.1).

Приказы, инструкции о мерах ПБ (общеобъектовые и по помещениям), планы
эвакуации, регламенты, декларация ПБ, журналы — с датой утверждения и сроком
пересмотра.

Почему своя таблица, а не ядровой ``document``: у того ``template_id`` NOT
NULL, поэтому документ, который платформа не выпускала (декларация, поданная в
МЧС; план эвакуации от подрядчика), в реестр ядра не заводится вовсе; вида
документа и срока пересмотра у ядра тоже нет. Ссылка на ядро сохранена полем
``document_id`` — если бумага всё-таки выпущена документной фабрикой.

Новая таблица — чисто additive-шаг (expand, правило OPS-74 разд. 74.2 по
построению). FK на site и document допустимы: это create_table, а не
add_column к существующей таблице (класс граблей wa02 сюда не относится).
Колонка ``version`` обязательна — модель наследует VersionedMixin (канон br01).

Revision ID: 20260824_fs05_fire_document
Revises: 20260824_sec65_rls_fire_maint
Create Date: 2026-08-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260824_fs05_fire_document"
down_revision = "20260824_sec65_rls_fire_maint"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fire_document",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.String(length=36),
            sa.ForeignKey("tenant.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("site_id", sa.String(length=36), sa.ForeignKey("site.id"), nullable=True),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("number", sa.String(length=64), nullable=True),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("approved_on", sa.Date(), nullable=True),
        sa.Column("review_due", sa.Date(), nullable=True),
        sa.Column("responsible", sa.String(length=255), nullable=True),
        sa.Column("document_id", sa.String(length=36), sa.ForeignKey("document.id"), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_fire_document_site_id", "fire_document", ["site_id"])
    op.create_index("ix_fire_document_tenant_kind", "fire_document", ["tenant_id", "kind"])
    op.create_index("ix_fire_document_tenant_review", "fire_document", ["tenant_id", "review_due"])


def downgrade() -> None:
    op.drop_index("ix_fire_document_tenant_review", table_name="fire_document")
    op.drop_index("ix_fire_document_tenant_kind", table_name="fire_document")
    op.drop_index("ix_fire_document_site_id", table_name="fire_document")
    op.drop_table("fire_document")
