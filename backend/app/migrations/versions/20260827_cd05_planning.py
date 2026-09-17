"""cd05: сведения по ГО и документы планирования (разд. 56.1).

Категория объекта по ГО НИГДЕ не хранилась, хотя мастер комплекта GOCHS_BASE
спрашивает её при каждом выпуске пакета (поле ``facility_category``), а
границы срезов 1–3 трижды на неё ссылались («сколько формирований нужно»,
«какова периодичность учений», «обязана ли организация создавать КЧС»).

Две таблицы:

* ``cd_profile`` — сведения по ГО об объекте: категория из закрытого словаря
  (четыре значения по постановлению Правительства) и реквизиты решения о
  категорировании. ОДНА карточка на площадку: двух решений о категорировании
  одного объекта не бывает — уникальность держит БАЗА;
* ``cd_document`` — учётная карточка документа планирования (планы ГО и
  действий по ЧС, паспорт безопасности, приказы, положения, инструкции) со
  сроком пересмотра. Ядровой ``Document`` не годится: у него ``template_id``
  NOT NULL, а план, утверждённый до внедрения платформы, ею не выпускался.

Новые таблицы — чисто additive-шаг (expand, правило OPS-74 разд. 74.2 по
построению). Колонка ``version`` обязательна — модели наследуют VersionedMixin
(канон br01).

Revision ID: 20260827_cd05_planning
Revises: 20260827_cd04_committee_kinds
Create Date: 2026-08-27
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260827_cd05_planning"
down_revision = "20260827_cd04_committee_kinds"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cd_profile",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.String(length=36),
            sa.ForeignKey("tenant.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("site_id", sa.String(length=36), sa.ForeignKey("site.id"), nullable=False),
        sa.Column("category", sa.String(length=16), nullable=False),
        sa.Column("decision_number", sa.String(length=128), nullable=True),
        sa.Column("decision_date", sa.Date(), nullable=True),
        sa.Column("responsible", sa.String(length=255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("tenant_id", "site_id", name="uq_cd_profile_site"),
    )
    op.create_index("ix_cd_profile_site_id", "cd_profile", ["site_id"])

    op.create_table(
        "cd_document",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.String(length=36),
            sa.ForeignKey("tenant.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("number", sa.String(length=64), nullable=True),
        sa.Column("site_id", sa.String(length=36), sa.ForeignKey("site.id"), nullable=True),
        sa.Column("approved_on", sa.Date(), nullable=True),
        sa.Column("review_due", sa.Date(), nullable=True),
        sa.Column("responsible", sa.String(length=255), nullable=True),
        sa.Column(
            "document_id",
            sa.String(length=36),
            sa.ForeignKey("document.id"),
            nullable=True,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_cd_document_site_id", "cd_document", ["site_id"])
    op.create_index("ix_cd_document_tenant_review", "cd_document", ["tenant_id", "review_due"])


def downgrade() -> None:
    op.drop_index("ix_cd_document_tenant_review", table_name="cd_document")
    op.drop_index("ix_cd_document_site_id", table_name="cd_document")
    op.drop_table("cd_document")
    op.drop_index("ix_cd_profile_site_id", table_name="cd_profile")
    op.drop_table("cd_profile")
