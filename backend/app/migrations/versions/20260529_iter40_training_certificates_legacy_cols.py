"""iter-40: training_certificates legacy backward-compat cols.

Closes one of the 5 column_drift_lite business-drift tables surfaced by
the audit (Session 85 baseline). The 4 cols + UniqueConstraint were
added to the ``TrainingCertificate`` model in commit ``58b428e`` ("Fix
training certificate model mapping for next APIs", 2026-03-09) but the
``training_certificates`` migration (``20260317_next46_training_briefings_offline.py:113``)
predates that commit and doesn't carry them.

Cols are:
    course_id    nullable FK → training_course.id  (ondelete=CASCADE)
    session_id   nullable FK → training_session.id (ondelete=SET NULL)
    plan_id      nullable FK → training_plan.id    (ondelete=SET NULL)
    number       nullable String(64)

Plus a UniqueConstraint(tenant_id, number).

The model marks these as ``# backward-compatible legacy fields``. They
are actively read/written by ``backend/app/api/routes/training.py``
(320, 321, 343, 373-375) and joined in ``backend/app/services/employee_card.py``
(328, 343). So they cannot be removed without API contract review.

iter-40 takes the safe path: add the cols + constraint to match the model
declaration. Mirror of iter-32's safe-subset business-drift cohort pattern
(PR #604) — nullable cols, no backfill, zero data risk.

After iter-40 lands the column_drift_lite business-drift count drops from
5 → 4 tables (incident, incident_log, incident_person, journalentry — the
remaining 4 are genuinely design-blocked).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260529_iter40_tc_legacy_cols"
down_revision: str | Sequence[str] | None = "20260529_iter38_server_default_c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # training_certificates.{course_id, session_id, plan_id, number} ---------
    op.add_column(
        "training_certificates",
        sa.Column(
            "course_id",
            sa.String(length=36),
            sa.ForeignKey("training_course.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    op.add_column(
        "training_certificates",
        sa.Column(
            "session_id",
            sa.String(length=36),
            sa.ForeignKey("training_session.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "training_certificates",
        sa.Column(
            "plan_id",
            sa.String(length=36),
            sa.ForeignKey("training_plan.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "training_certificates",
        sa.Column("number", sa.String(length=64), nullable=True),
    )

    op.create_index(
        "ix_training_certificates_course_id",
        "training_certificates",
        ["course_id"],
        unique=False,
    )
    op.create_index(
        "ix_training_certificates_session_id",
        "training_certificates",
        ["session_id"],
        unique=False,
    )
    op.create_index(
        "ix_training_certificates_plan_id",
        "training_certificates",
        ["plan_id"],
        unique=False,
    )

    op.create_unique_constraint(
        "uq_training_certificate_number",
        "training_certificates",
        ["tenant_id", "number"],
    )


def downgrade() -> None:
    # Reverse order so downstream tooling observes inverse symmetry.
    op.drop_constraint(
        "uq_training_certificate_number",
        "training_certificates",
        type_="unique",
    )
    op.drop_index(
        "ix_training_certificates_plan_id",
        table_name="training_certificates",
    )
    op.drop_index(
        "ix_training_certificates_session_id",
        table_name="training_certificates",
    )
    op.drop_index(
        "ix_training_certificates_course_id",
        table_name="training_certificates",
    )
    op.drop_column("training_certificates", "number")
    op.drop_column("training_certificates", "plan_id")
    op.drop_column("training_certificates", "session_id")
    op.drop_column("training_certificates", "course_id")
