"""wa07: batch unique key includes location (partial transfers between locations).

Drops uq_ppe_stock_batch_item_no (tenant, item, batch_no) and replaces it with a
unique index over (tenant, item, batch_no, location) using NULLS NOT DISTINCT so a
batch_no can live in several locations while legacy NULL-location batches keep their
old dedup guarantee. Not purely additive (swaps a constraint) — PG16-gate verified.
"""

from __future__ import annotations

from alembic import op

revision = "20260704_wa07_ppe_stock_batch_location_unique"
down_revision = "20260703_wa06_ppe_inventory_count"
branch_labels = None
depends_on = None

_TABLE = "ppe_stock_batch"


def upgrade() -> None:
    op.drop_constraint("uq_ppe_stock_batch_item_no", _TABLE, type_="unique")
    op.create_index(
        "uq_ppe_stock_batch_item_no_loc",
        _TABLE,
        ["tenant_id", "item_id", "batch_no", "location"],
        unique=True,
        postgresql_nulls_not_distinct=True,
    )


def downgrade() -> None:
    op.drop_index("uq_ppe_stock_batch_item_no_loc", table_name=_TABLE)
    op.create_unique_constraint("uq_ppe_stock_batch_item_no", _TABLE, ["tenant_id", "item_id", "batch_no"])
