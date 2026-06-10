"""sz01: СИЗ Срез-1 — norms→catalog link, 766н card requisites, VARCHAR status.

Additive columns + one in-place type conversion:
  * ppenorm.item_id            (nullable FK-like ref to ppeitem; legacy rows keep item_name only)
  * person.ppe_sizes           (JSON, 766н sizes/anthropometry)
  * ppeissue: certificate_no / wear_percent / return_wear_percent /
              signature_doc_ref / writeoff_reason / replaces_issue_id
  * ppeissue.status: native enum ppeissuestatus -> VARCHAR(32), data lowercased,
    orphan PG type dropped (анти-грабли: VARCHAR convention, see con01/med01).

Downgrade is honest about asymmetry: it refuses when written_off/replaced rows
exist (those values are unrepresentable in the old 3-value enum).
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260610_sz01_ppe_norms_card_766n"
down_revision = "20260610_con02_contractor_document_requirements"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    # --- additive columns ----------------------------------------------
    op.add_column("ppenorm", sa.Column("item_id", sa.String(length=36), nullable=True))
    op.create_index("ix_ppenorm_item_id", "ppenorm", ["item_id"])

    op.add_column("person", sa.Column("ppe_sizes", sa.JSON(), nullable=True))

    op.add_column("ppeissue", sa.Column("certificate_no", sa.String(length=255), nullable=True))
    op.add_column("ppeissue", sa.Column("wear_percent", sa.Integer(), nullable=True))
    op.add_column("ppeissue", sa.Column("return_wear_percent", sa.Integer(), nullable=True))
    op.add_column("ppeissue", sa.Column("signature_doc_ref", sa.String(length=255), nullable=True))
    op.add_column("ppeissue", sa.Column("writeoff_reason", sa.String(length=255), nullable=True))
    op.add_column("ppeissue", sa.Column("replaces_issue_id", sa.String(length=36), nullable=True))
    op.create_index("ix_ppeissue_replaces_issue_id", "ppeissue", ["replaces_issue_id"])

    # --- status: native enum -> VARCHAR(32), lowercase ------------------
    if dialect == "postgresql":
        op.execute(
            "ALTER TABLE ppeissue ALTER COLUMN status TYPE VARCHAR(32) "
            "USING lower(status::text)"
        )
        op.execute("ALTER TABLE ppeissue ALTER COLUMN status SET DEFAULT 'issued'")
        op.execute("DROP TYPE IF EXISTS ppeissuestatus")
    else:
        # SQLite: Enum is already stored as VARCHAR; just normalise case.
        with op.batch_alter_table("ppeissue") as batch:
            batch.alter_column(
                "status",
                existing_type=sa.String(length=32),
                type_=sa.String(length=32),
                existing_nullable=False,
            )
        op.execute("UPDATE ppeissue SET status = lower(status)")


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    # written_off / replaced are unrepresentable in the legacy 3-value enum.
    blockers = bind.execute(
        sa.text(
            "SELECT COUNT(*) FROM ppeissue WHERE status IN ('written_off', 'replaced')"
        )
    ).scalar()
    if blockers:
        raise RuntimeError(
            "cannot downgrade sz01: ppeissue contains written_off/replaced rows "
            f"({blockers}); resolve them before downgrading"
        )

    if dialect == "postgresql":
        op.execute("ALTER TABLE ppeissue ALTER COLUMN status DROP DEFAULT")
        op.execute("CREATE TYPE ppeissuestatus AS ENUM ('ISSUED', 'RETURNED', 'LOST')")
        op.execute(
            "ALTER TABLE ppeissue ALTER COLUMN status TYPE ppeissuestatus "
            "USING upper(status)::ppeissuestatus"
        )
    else:
        op.execute("UPDATE ppeissue SET status = upper(status)")

    op.drop_index("ix_ppeissue_replaces_issue_id", table_name="ppeissue")
    op.drop_column("ppeissue", "replaces_issue_id")
    op.drop_column("ppeissue", "writeoff_reason")
    op.drop_column("ppeissue", "signature_doc_ref")
    op.drop_column("ppeissue", "return_wear_percent")
    op.drop_column("ppeissue", "wear_percent")
    op.drop_column("ppeissue", "certificate_no")
    op.drop_column("person", "ppe_sizes")
    op.drop_index("ix_ppenorm_item_id", table_name="ppenorm")
    op.drop_column("ppenorm", "item_id")
