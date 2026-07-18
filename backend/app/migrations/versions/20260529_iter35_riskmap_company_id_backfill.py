"""iter-35: backfill riskmap.company_id NOT NULL FK + matching unique constraint.

Revision ID: 20260529_iter35_riskmap_company
Revises: 20260529_iter34_ppenorm_hazard
Create Date: 2026-05-29

Sibling of iter-34. Closes the second of the two NOT-NULL FK items iter-32
explicitly deferred (line 30 of iter-32 docstring)::

    riskmap:   company_id   (NOT NULL FK — no safe server_default)

Bug class: ORM-Migration drift, flavor (b) — column declared on the model
(``models.py::RiskMap.company_id``) but absent from the creator migration
(``6b6dee7c951f_initial_schema.py`` line 484 ``op.create_table('riskmap',
...)`` lists methodology_id/matrix/recalculated_at/tenant_id/version/id
— no company_id).

Strategy (mirrors iter-34's 3-step in-migration pattern):

    Step 1: ADD COLUMN company_id (nullable=True) + FK + index.
    Step 2: ``DELETE FROM riskmap WHERE company_id IS NULL`` — same
            justification as iter-34: table was effectively read-only
            since deploy (Postgres ``UndefinedColumnError`` on every
            ORM INSERT); SQLite-tolerant rows lack a meaningful
            company_id.
    Step 3: ``ALTER COLUMN company_id SET NOT NULL`` (batch_alter for
            SQLite portability).

Plus matching ``UniqueConstraint(tenant_id, company_id, site_id,
position_id, methodology_id, name='uq_riskmap_scope')`` per model
``__table_args__``. All five columns exist by end of upgrade:

    - tenant_id, methodology_id  : initial schema (line 484)
    - site_id, position_id       : iter-32 (nullable add)
    - company_id                 : this migration

Important contrast with iter-34: the FK has **no ondelete** because the
model declaration is ``ForeignKey("company.id")`` with no ondelete
parameter — migration must mirror the model exactly.

Downgrade is the strict inverse: drop unique → drop index → drop column.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260529_iter35_riskmap_company"
down_revision: str | Sequence[str] | None = "20260529_iter34_ppenorm_hazard"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Step 1: add nullable column + FK + index (no ondelete — see docstring).
    op.add_column(
        "riskmap",
        sa.Column(
            "company_id",
            sa.String(length=36),
            sa.ForeignKey("company.id"),
            nullable=True,
        ),
    )
    op.create_index("ix_riskmap_company_id", "riskmap", ["company_id"], unique=False)

    # Step 2: discard stale rows that pre-date the column. See docstring.
    op.execute("DELETE FROM riskmap WHERE company_id IS NULL")

    # Step 3: tighten to NOT NULL. batch_alter_table for SQLite portability.
    with op.batch_alter_table("riskmap") as batch_op:
        batch_op.alter_column(
            "company_id",
            existing_type=sa.String(length=36),
            nullable=False,
        )

    # Model invariant — uq_riskmap_scope spans all five scope columns.
    with op.batch_alter_table("riskmap") as batch_op:
        batch_op.create_unique_constraint(
            "uq_riskmap_scope",
            ["tenant_id", "company_id", "site_id", "position_id", "methodology_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("riskmap") as batch_op:
        batch_op.drop_constraint("uq_riskmap_scope", type_="unique")
    op.drop_index("ix_riskmap_company_id", table_name="riskmap")
    op.drop_column("riskmap", "company_id")
