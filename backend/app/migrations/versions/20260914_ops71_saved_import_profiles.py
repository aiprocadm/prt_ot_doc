"""OPS-71 (срез-192): профиль импорта, заведённый самим арендатором.

Revision ID: 20260914_ops71_saved_import_profiles
Revises: 20260914_ops73_endpoint_schema_version
Create Date: 2026-09-14

Остаток строки: «профили конкурентов (нужны образцы их выгрузок — вопрос
владельцу)». То есть поддержка каждого нового формата упиралась сразу в две
вещи: достать чужой файл и написать под него код.

Образцы не нужны. У клиента, который переезжает, его выгрузка уже есть. Он один
раз сопоставляет колонки руками и сохраняет сопоставление профилем; в следующий
раз файл той же формы опознаётся сам. Система учится у того, у кого файл
действительно есть.

Строка принадлежит арендатору: формат выгрузки — это его знание о своей прошлой
системе, и делиться им между арендаторами нельзя (в заголовках встречаются
названия подразделений и фамилии).

Миграция добавляющая: новая таблица, существующие не трогаются.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260914_ops71_saved_import_profiles"
down_revision: str | Sequence[str] | None = "20260914_ops73_endpoint_schema_version"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "import_profiles",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("target", sa.String(length=64), nullable=False),
        sa.Column("mapping", sa.JSON(), nullable=False),
        sa.Column("splits", sa.JSON(), nullable=False),
        sa.Column("signature", sa.JSON(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.UniqueConstraint("tenant_id", "code", name="uq_import_profiles_tenant_code"),
    )
    op.create_index("ix_import_profiles_tenant_id", "import_profiles", ["tenant_id"])
    op.create_index(
        "ix_import_profiles_tenant_target", "import_profiles", ["tenant_id", "target"]
    )


def downgrade() -> None:
    op.drop_index("ix_import_profiles_tenant_target", table_name="import_profiles")
    op.drop_index("ix_import_profiles_tenant_id", table_name="import_profiles")
    op.drop_table("import_profiles")
