"""Expand outbox for outbound traffic dispatch.

Revision ID: 20250325_outbox_outbound_traffic
Revises: 20250321_outbox_dedupe_key
Create Date: 2025-03-25 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20250325_outbox_outbound_traffic"
down_revision: str | tuple[str, ...] = "20250321_outbox_dedupe_key"
branch_labels: str | None = None
depends_on: str | None = None


_OUTBOX_STATUS = postgresql.ENUM(
    "PENDING",
    "IN_PROGRESS",
    "SENT",
    "FAILED",
    "DEAD",
    name="outboxstatus",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    _OUTBOX_STATUS.create(bind, checkfirst=True)
    with op.batch_alter_table("outbox", schema=None) as batch:
        batch.add_column(sa.Column("destination", sa.String(length=512), nullable=False, server_default="webhook"))
        batch.add_column(sa.Column("headers", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("idempotency_key", sa.String(length=128), nullable=True))
        batch.add_column(sa.Column("status", _OUTBOX_STATUS, nullable=False, server_default="PENDING"))
        batch.add_column(sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True, server_default=sa.text("CURRENT_TIMESTAMP")))
        # NOTE: PostgreSQL refuses to ALTER COLUMN ... TYPE JSON without an explicit
        # USING clause unless every existing value is already valid JSON (TEXT → JSON
        # is a non-trivial cast). The previous String(512) column held free-form
        # error strings such as "connection reset by peer", which are not valid JSON
        # documents. SQLite silently accepted the cast because its JSON column is
        # really TEXT with json1 extension validation only on read. Wrap legacy
        # values as ``{"message": "..."}`` so the cast succeeds AND structured
        # downstream consumers can rely on object shape going forward.
        batch.alter_column(
            "last_error",
            type_=sa.JSON(),
            existing_type=sa.String(length=512),
            nullable=True,
            postgresql_using=(
                "CASE WHEN last_error IS NULL THEN NULL "
                "ELSE jsonb_build_object('message', last_error)::json END"
            ),
        )
        batch.alter_column("processed_at", new_column_name="sent_at")
        batch.drop_index("ix_outbox_processed_at")
        batch.drop_constraint("uq_outbox_dedupe", type_="unique")
        batch.create_index("ix_outbox_status_next_attempt", ["status", "next_attempt_at"], unique=False)
        batch.create_index("ix_outbox_event_type", ["event_type"], unique=False)
        batch.create_index("ix_outbox_idempotency_key", ["idempotency_key"], unique=False)
        batch.create_unique_constraint(
            "uq_outbox_idempotency",
            ["tenant_id", "destination", "idempotency_key"],
        )

    op.execute("UPDATE outbox SET idempotency_key = dedupe_key WHERE dedupe_key IS NOT NULL")
    op.execute("UPDATE outbox SET status = 'SENT' WHERE sent_at IS NOT NULL")
    op.execute("UPDATE outbox SET status = 'PENDING' WHERE sent_at IS NULL")
    op.execute("UPDATE outbox SET next_attempt_at = created_at WHERE next_attempt_at IS NULL")

    with op.batch_alter_table("outbox", schema=None) as batch:
        batch.drop_column("dedupe_key")
        batch.alter_column("destination", server_default=None)
        batch.alter_column("status", server_default=None)
        batch.alter_column("next_attempt_at", server_default=None)



def downgrade() -> None:
    bind = op.get_bind()
    with op.batch_alter_table("outbox", schema=None) as batch:
        batch.add_column(sa.Column("dedupe_key", sa.String(length=128), nullable=True))
        batch.drop_constraint("uq_outbox_idempotency", type_="unique")
        batch.drop_index("ix_outbox_idempotency_key")
        batch.drop_index("ix_outbox_event_type")
        batch.drop_index("ix_outbox_status_next_attempt")
        batch.alter_column("sent_at", new_column_name="processed_at")
        batch.alter_column("last_error", type_=sa.String(length=512), existing_type=sa.JSON(), nullable=True)
        batch.drop_column("next_attempt_at")
        batch.drop_column("status")
        batch.drop_column("idempotency_key")
        batch.drop_column("headers")
        batch.drop_column("destination")
        batch.create_index("ix_outbox_processed_at", ["processed_at"], unique=False)
        batch.create_unique_constraint(
            "uq_outbox_dedupe",
            ["tenant_id", "event_type", "dedupe_key"],
        )

    op.execute("UPDATE outbox SET processed_at = NULL WHERE processed_at IS NOT NULL")
    _OUTBOX_STATUS.drop(bind, checkfirst=True)
