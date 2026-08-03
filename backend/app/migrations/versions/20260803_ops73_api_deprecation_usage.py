"""OPS-73 срез-3: api_deprecation_usage — кто ещё ходит в устаревшие поверхности.

Платформенная таблица (tenant-слуг строкой, БЕЗ tenant_id/FK — вне RLS-контура:
данные видит только платформенный админ, а слуг из заголовка может быть
неизвестным). Additive; честный downgrade.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260803_ops73_api_deprecation_usage"
down_revision = "20260803_sec65_rls_committee_invitation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "api_deprecation_usage",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tenant_slug", sa.String(length=64), nullable=False, index=True),
        sa.Column("path_prefix", sa.String(length=255), nullable=False, index=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("hits_2xx", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("tenant_slug", "path_prefix", name="uq_api_deprecation_usage"),
    )


def downgrade() -> None:
    op.drop_table("api_deprecation_usage")
