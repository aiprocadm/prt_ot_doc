"""prm01: personal permit status native enum -> VARCHAR(32), lowercase.

In-place type conversion mirroring sz01 (ppeissue.status). The legacy enum
``permitstatus`` already covers all three values (active/expired/revoked),
so downgrade is fully reversible — no data blocker is needed.
"""

from __future__ import annotations

from alembic import op

revision = "20260615_prm01_permit_status_varchar"
down_revision = "20260614_drift01_orm_pg_column_closure"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "postgresql":
        op.execute(
            "ALTER TABLE permit ALTER COLUMN status TYPE VARCHAR(32) " "USING lower(status::text)"
        )
        op.execute("ALTER TABLE permit ALTER COLUMN status SET DEFAULT 'active'")
        op.execute("DROP TYPE IF EXISTS permitstatus")
    else:
        # SQLite stores Enum as VARCHAR and does not enforce length — just normalise case.
        op.execute("UPDATE permit SET status = lower(status)")


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "postgresql":
        op.execute("ALTER TABLE permit ALTER COLUMN status DROP DEFAULT")
        op.execute("CREATE TYPE permitstatus AS ENUM ('ACTIVE', 'EXPIRED', 'REVOKED')")
        op.execute(
            "ALTER TABLE permit ALTER COLUMN status TYPE permitstatus "
            "USING upper(status)::permitstatus"
        )
        op.execute("ALTER TABLE permit ALTER COLUMN status SET DEFAULT 'ACTIVE'")
    else:
        op.execute("UPDATE permit SET status = upper(status)")
