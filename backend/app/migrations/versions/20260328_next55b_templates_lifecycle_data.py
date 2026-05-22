"""NEXT-55b templates lifecycle data backfill

Revision ID: 20260328_next55b
Revises: 20260328_next55
Create Date: 2026-05-22

PG12+ forbids using a newly-added enum value in the same transaction where it
was added via ALTER TYPE ADD VALUE. The 4 new values (UPLOADED/LINTED/READY/
DEPRECATED) are added in 20260328_next55; this revision runs in a fresh
transaction so the catalog sees the values as committed and the UPDATE on
templateversion.status is safe.
"""

from alembic import op


revision = "20260328_next55b"
down_revision = "20260328_next55"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE templateversion SET status = 'UPLOADED'")


def downgrade() -> None:
    pass
