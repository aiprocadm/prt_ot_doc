"""ed01: PEP signing columns on signature_requests (ЭДО Срез-1, vNext §6.9).

Additive: the polymorphic signature_requests table (next57) gains the PEP
internal-signature fields — signer person, canonical content hash, purpose,
one-time confirm-code state — plus a status widening VARCHAR(16)->VARCHAR(32)
for the new awaiting_code/declined/expired values. New rows are written with
signature_type='pep', provider='internal'; legacy kep/unep rows are untouched.

Downgrade drops the six columns and (on PG) restores the native enum type;
it refuses to run while rows carry the new PEP statuses
(awaiting_code/declined/expired) and the enum cast is a second honest-failure
line. On SQLite status just narrows back to VARCHAR(16).

Note on status column type: next30 created it as PG ENUM signaturerequeststatus
(created/requested/signed/failed); the ORM now uses String(16) (known drift).
On SQLite the existing_type is String(16) (SQLite has no native ENUM). On PG
we use raw ALTER TABLE with USING cast to avoid enum-vs-varchar conflicts; the
orphaned enum type is dropped after widening (anti-footgun from PR #639).
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260611_ed01_pep_signing_columns"
down_revision = "20260611_sz02_drop_ppe_family_b_tables"
branch_labels = None
depends_on = None

TABLE = "signature_requests"


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    op.add_column(TABLE, sa.Column("signer_person_id", sa.String(length=36), nullable=True))
    op.add_column(TABLE, sa.Column("content_hash", sa.String(length=64), nullable=True))
    op.add_column(TABLE, sa.Column("purpose", sa.String(length=32), nullable=True))
    op.add_column(TABLE, sa.Column("confirm_code_hash", sa.String(length=64), nullable=True))
    op.add_column(TABLE, sa.Column("confirm_code_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(TABLE, sa.Column("confirm_attempts", sa.Integer(), nullable=False, server_default="0"))
    op.create_index("ix_signature_requests_signer_person_id", TABLE, ["signer_person_id"])
    if dialect == "postgresql":
        op.create_foreign_key(
            "fk_signature_requests_signer_person_id_person",
            TABLE,
            "person",
            ["signer_person_id"],
            ["id"],
            ondelete="SET NULL",
        )
        op.execute(f"ALTER TABLE {TABLE} ALTER COLUMN status TYPE VARCHAR(32) USING status::text")
        op.execute("DROP TYPE IF EXISTS signaturerequeststatus")
    else:
        with op.batch_alter_table(TABLE) as batch:
            batch.alter_column(
                "status",
                existing_type=sa.String(length=16),
                type_=sa.String(length=32),
                existing_nullable=False,
            )


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    blockers = bind.execute(
        sa.text(
            "SELECT COUNT(*) FROM signature_requests "
            "WHERE status IN ('awaiting_code', 'declined', 'expired')"
        )
    ).scalar()
    if blockers:
        raise RuntimeError(
            "ed01 downgrade blocked: signature_requests contains PEP statuses "
            "(awaiting_code/declined/expired) unknown to the pre-ed01 enum; "
            f"rows={blockers}"
        )

    if dialect == "postgresql":
        op.drop_constraint("fk_signature_requests_signer_person_id_person", TABLE, type_="foreignkey")
        op.execute("CREATE TYPE signaturerequeststatus AS ENUM ('created', 'requested', 'signed', 'failed')")
        op.execute(
            f"ALTER TABLE {TABLE} ALTER COLUMN status TYPE signaturerequeststatus "
            "USING status::signaturerequeststatus"
        )
    else:
        with op.batch_alter_table(TABLE) as batch:
            batch.alter_column(
                "status",
                existing_type=sa.String(length=32),
                type_=sa.String(length=16),
                existing_nullable=False,
            )
    op.drop_index("ix_signature_requests_signer_person_id", table_name=TABLE)
    op.drop_column(TABLE, "confirm_attempts")
    op.drop_column(TABLE, "confirm_code_expires_at")
    op.drop_column(TABLE, "confirm_code_hash")
    op.drop_column(TABLE, "purpose")
    op.drop_column(TABLE, "content_hash")
    op.drop_column(TABLE, "signer_person_id")
