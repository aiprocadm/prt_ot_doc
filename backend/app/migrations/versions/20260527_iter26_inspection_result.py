"""iter-26: add inspection_result table missing from migrations.

Revision ID: 20260527_iter26_inspection_result
Revises: 20260527_iter25_training_family
Create Date: 2026-05-27

Standalone critical drift surfaced by ``scripts/audit/check_orm_migration_drift.py``.
After iter-25 closed the training-family cohort (RB-002o/p/q), the audit
``--summary`` reports 3 remaining critical drifts: ``incident_log``,
``incident_person``, and ``inspection_result``. The two ``incident_*`` tables
are deferred because the parent ``incident`` table itself has business drift
(7 missing cols incl. String→Enum migrations for status/stage/person_role)
that requires its own enum-design pass — A3 antipattern territory.

``inspection_result`` is the only critical with zero entanglement on the
incident family. Both FK targets exist:
  - ``regulatory_inspection`` (created in ``20250415_create_regulatory_inspection_base.py``)
  - ``file`` (created in ``6b6dee7c951f_initial_schema.py``)

Model: ``backend/app/models/models.py:2455`` (``InspectionResult``,
``TenantBaseModel + SoftDeleteMixin``). Bound to ``regulatory_inspection``
via ``cascade="all, delete-orphan"`` on the parent side — so CASCADE on
the FK matches ORM expectation.

No new enum types — InspectionResult has no enum columns. ``outcome`` is
a plain String(128) (the parent ``regulatory_inspection.status`` enum
``regulatoryinspectionstatus`` was created back in its own migration).

Antipattern guards:
  - A1 (enum double-create): not applicable — no new enums.
  - Alembic head: verified ``20260527_iter25_training_family`` is the
    current head (this branch is stacked on iter-25 PR #594).

Cohort rationale: standalone (no cohort). Bundling with incident_log /
incident_person would require finishing incident parent business-drift
first — separate multi-iter work. This iter is intentionally narrow
to keep iter-25 momentum without taking on enum-design risk.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260527_iter26_inspection_result"
down_revision: str | Sequence[str] | None = "20260527_iter25_training_family"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "inspection_result",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("inspection_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("outcome", sa.String(length=128), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("issued_at", sa.Date(), nullable=True),
        sa.Column("file_id", sa.String(length=36), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], name="fk_inspection_result_tenant"),
        sa.ForeignKeyConstraint(
            ["inspection_id"],
            ["regulatory_inspection.id"],
            name="fk_inspection_result_inspection",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["file_id"],
            ["file.id"],
            name="fk_inspection_result_file",
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_inspection_result_tenant_id",
        "inspection_result",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        "ix_inspection_result_inspection_id",
        "inspection_result",
        ["inspection_id"],
        unique=False,
    )
    op.create_index(
        "ix_inspection_result_inspection",
        "inspection_result",
        ["tenant_id", "inspection_id"],
        unique=False,
    )
    op.create_index(
        "ix_inspection_result_issued_at",
        "inspection_result",
        ["issued_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_inspection_result_issued_at", table_name="inspection_result")
    op.drop_index("ix_inspection_result_inspection", table_name="inspection_result")
    op.drop_index("ix_inspection_result_inspection_id", table_name="inspection_result")
    op.drop_index("ix_inspection_result_tenant_id", table_name="inspection_result")
    op.drop_table("inspection_result")
