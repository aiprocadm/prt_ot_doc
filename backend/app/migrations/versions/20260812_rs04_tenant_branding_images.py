"""rs04: логотип и favicon в бренде арендатора (BIZ-52 срез-6).

Доп. №1 разд. 52.2, первый пункт: «логотип, название, цветовая тема, favicon».
Имя и цвет доехали срезом-4 (rs02); здесь — картинки. Additive: четыре nullable
колонки в существующей таблице, ни одна строка не меняет смысл.

Картинки хранятся В СТРОКЕ, а не в файловом контуре: общий контур требует MinIO
и антивирусный карантин, а логотип — маленькая публичная картинка с жёстким
потолком размера, которую отдают клиентам ЧУЖОГО арендатора (клиент партнёра
видит логотип партнёра) — общая выдача файлов такое запрещает намеренно.

RLS уже стоит на таблице с rs02 и действует на СТРОКИ — новые колонки
подхватываются политикой автоматически, отдельного шага не нужно.

Revision ID: 20260812_rs04_tenant_branding_images
Revises: 20260812_rs03_tenant_legal_document
Create Date: 2026-08-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260812_rs04_tenant_branding_images"
down_revision = "20260812_rs03_tenant_legal_document"
branch_labels = None
depends_on = None

_TABLE = "tenant_branding"


def upgrade() -> None:
    op.add_column(_TABLE, sa.Column("logo_image", sa.LargeBinary(), nullable=True))
    op.add_column(_TABLE, sa.Column("logo_media_type", sa.String(length=64), nullable=True))
    op.add_column(_TABLE, sa.Column("favicon_image", sa.LargeBinary(), nullable=True))
    op.add_column(_TABLE, sa.Column("favicon_media_type", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column(_TABLE, "favicon_media_type")
    op.drop_column(_TABLE, "favicon_image")
    op.drop_column(_TABLE, "logo_media_type")
    op.drop_column(_TABLE, "logo_image")
