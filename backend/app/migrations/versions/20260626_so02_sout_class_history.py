"""so02: СОУТ срез-2 — class-of-conditions history (additive, P10-04 / TZ B.10).

Single additive table ``sout_class_history`` (append-only audit of
``assessed_class`` changes per workplace). ``soutclass`` enum already exists
(created by so01) → referenced with ``create_type=False``. Honest downgrade
drops the table only (shared enum is owned by so01).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260626_so02_sout_class_history"
down_revision = "20260626_so01_sout"
branch_labels = None
depends_on = None


# soutclass already created by so01 — reference without re-emitting DDL.
# ВАЖНО: dialect-specific ``postgresql.ENUM(create_type=False)``, а НЕ generic
# ``sa.Enum``: только у первого create_type=False надёжно подавляет неявный
# ``CREATE TYPE`` в ``op.create_table`` (иначе ``DuplicateObjectError: type
# "soutclass" already exists`` на PostgreSQL; на SQLite невидимо). Один объект
# безопасно переиспользуется обеими колонками (old_class/new_class) — DDL нет.
_SOUT_CLASS = postgresql.ENUM(
    "optimal",
    "acceptable",
    "harmful_3_1",
    "harmful_3_2",
    "harmful_3_3",
    "harmful_3_4",
    "dangerous",
    name="soutclass",
    create_type=False,
)


def upgrade() -> None:
    op.create_table(
        "sout_class_history",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.String(length=36),
            sa.ForeignKey("tenant.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "workplace_id",
            sa.String(length=36),
            sa.ForeignKey("sout_workplace.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("old_class", _SOUT_CLASS, nullable=True),
        sa.Column("new_class", _SOUT_CLASS, nullable=True),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("sout_class_history")
