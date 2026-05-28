"""iter-34: backfill ppenorm.hazard_id NOT NULL FK + matching unique constraint.

Revision ID: 20260529_iter34_ppenorm_hazard
Revises: 20260528_iter32_business_drift
Create Date: 2026-05-29

Continuation of iter-32 deferred work. The iter-32 docstring explicitly
listed::

    ppenorm:   hazard_id    (NOT NULL FK — no safe server_default)

as a follow-up because every other column in that cohort could ship under
nullable or server_default semantics, but ``hazard_id`` has neither — it
is required in ``models.py::PPENorm`` with no Python-side default and
with FK ``risk_hazards.id ondelete=CASCADE``.

Bug class: ORM-Migration drift, flavor (b) — column declared on the model
but absent from the creator migration (``6b6dee7c951f_initial_schema.py``
line 620 ``op.create_table('ppenorm', ...)`` lists position_id, item_name,
quantity, interval_days, tenant_id, version, id — but no hazard_id).

Strategy (3 in-migration steps):

    Step 1: ADD COLUMN hazard_id (nullable=True) + FK + index.
            Postgres rejects ADD COLUMN NOT NULL without server_default
            against a non-empty table; the staged approach keeps the
            migration portable.

    Step 2: ``DELETE FROM ppenorm WHERE hazard_id IS NULL`` — clean up
            any stale rows. Justification: the table has been effectively
            read-only since deploy (every ORM INSERT broke on Postgres
            ``UndefinedColumnError`` per iter-32 docstring); SQLite was
            tolerant but any rows it accepted have no meaningful
            hazard_id and would violate the model's NOT NULL invariant
            anyway.

    Step 3: ``ALTER COLUMN hazard_id SET NOT NULL`` — wrapped in
            batch_alter_table for SQLite portability.

Plus matching ``UniqueConstraint(tenant_id, position_id, hazard_id,
item_name, name='uq_ppe_norm_position_hazard_item')`` per the model
``__table_args__`` — hazard_id is part of the model's uniqueness tuple
so the DB must enforce the same invariant.

Downgrade is the strict inverse: drop unique → drop index → drop column.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260529_iter34_ppenorm_hazard"
down_revision: str | Sequence[str] | None = "20260528_iter32_business_drift"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Step 1: add nullable column + FK + index.
    op.add_column(
        "ppenorm",
        sa.Column(
            "hazard_id",
            sa.String(length=36),
            sa.ForeignKey("risk_hazards.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    op.create_index("ix_ppenorm_hazard_id", "ppenorm", ["hazard_id"], unique=False)

    # Step 2: discard stale rows that pre-date the column. See docstring.
    op.execute("DELETE FROM ppenorm WHERE hazard_id IS NULL")

    # Step 3: tighten to NOT NULL. batch_alter_table for SQLite portability.
    with op.batch_alter_table("ppenorm") as batch_op:
        batch_op.alter_column(
            "hazard_id",
            existing_type=sa.String(length=36),
            nullable=False,
        )

    # Model invariant — must be enforced at DB level.
    with op.batch_alter_table("ppenorm") as batch_op:
        batch_op.create_unique_constraint(
            "uq_ppe_norm_position_hazard_item",
            ["tenant_id", "position_id", "hazard_id", "item_name"],
        )


def downgrade() -> None:
    with op.batch_alter_table("ppenorm") as batch_op:
        batch_op.drop_constraint("uq_ppe_norm_position_hazard_item", type_="unique")
    op.drop_index("ix_ppenorm_hazard_id", table_name="ppenorm")
    op.drop_column("ppenorm", "hazard_id")
