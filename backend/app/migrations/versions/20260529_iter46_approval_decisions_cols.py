"""iter-46: approval_decisions model-col closure.

Closes the ``approval_decisions`` business-drift table surfaced by
``column_drift_lite`` (Session 94 candidate #2). Five columns were added to
the ``ApprovalDecision`` model over the orchestration build-out
(``backend/app/models/approval_workflow.py:170-178``) but the only migration
that touches the table — ``20250425_edo_approval_signature_mvp.py:130`` —
predates them and creates just ``request_id, step_index, actor_user_id,
decision, comment`` + base cols.

Cols are:
    approval_instance_id        nullable FK -> approval_instances.id       (index)
    approval_instance_step_id   nullable FK -> approval_instance_steps.id  (index)
    payload_json                nullable JSON
    ip                          nullable String(64)
    user_agent                  nullable String(512)

These are live read/written: ``app/modules/approvals/service.py:140-148``
constructs ``ApprovalDecision(approval_instance_id=..., approval_instance_step_id=...)``
and ``app/api/routes/approval_orchestration.py:293`` filters on
``approval_instance_id``. So they are real drift — not removable without API
contract review. iter-46 takes the safe path: add the cols + indexes to match
the model declaration (nullable, no backfill, zero data risk). Mirror of
iter-40's safe-subset business-drift pattern (PR #604).

Ordering note (differs from iter-40): the table itself (mvp) and the FK-target
tables ``approval_instances`` / ``approval_instance_steps`` (next57) live on a
DIFFERENT branch than this migration's ``down_revision`` (iter38). Under
``alembic upgrade heads`` cross-branch ordering is guaranteed only by
``depends_on``, so iter-46 declares an explicit dependency on both. The two FK
columns carry NO ondelete clause — matching the bare ``ForeignKey(...)`` in the
model (unlike iter-40's CASCADE/SET NULL cohort).

After iter-46 lands the column_drift_lite business-drift count drops from
3 -> 2 tables (file, outbox_events — the remaining iter-47 / iter-48 candidates).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260529_iter46_approval_decisions_cols"
down_revision: str | Sequence[str] | None = "20260529_iter38_server_default_c"
branch_labels: str | Sequence[str] | None = None
# mvp creates approval_decisions; next57 creates the FK-target tables. Both sit
# on a different branch than iter38 — depends_on forces correct ordering under
# `alembic upgrade heads`.
depends_on: str | Sequence[str] | None = (
    "20250425_edo_approval_signature_mvp",
    "20260330_next57",
)


def upgrade() -> None:
    # approval_decisions.{approval_instance_id, approval_instance_step_id,
    #                     payload_json, ip, user_agent} -----------------------
    op.add_column(
        "approval_decisions",
        sa.Column(
            "approval_instance_id",
            sa.String(length=36),
            sa.ForeignKey("approval_instances.id"),
            nullable=True,
        ),
    )
    op.add_column(
        "approval_decisions",
        sa.Column(
            "approval_instance_step_id",
            sa.String(length=36),
            sa.ForeignKey("approval_instance_steps.id"),
            nullable=True,
        ),
    )
    op.add_column(
        "approval_decisions",
        sa.Column("payload_json", sa.JSON(), nullable=True),
    )
    op.add_column(
        "approval_decisions",
        sa.Column("ip", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "approval_decisions",
        sa.Column("user_agent", sa.String(length=512), nullable=True),
    )

    op.create_index(
        "ix_approval_decisions_approval_instance_id",
        "approval_decisions",
        ["approval_instance_id"],
        unique=False,
    )
    op.create_index(
        "ix_approval_decisions_approval_instance_step_id",
        "approval_decisions",
        ["approval_instance_step_id"],
        unique=False,
    )


def downgrade() -> None:
    # Reverse order so downstream tooling observes inverse symmetry.
    op.drop_index(
        "ix_approval_decisions_approval_instance_step_id",
        table_name="approval_decisions",
    )
    op.drop_index(
        "ix_approval_decisions_approval_instance_id",
        table_name="approval_decisions",
    )
    op.drop_column("approval_decisions", "user_agent")
    op.drop_column("approval_decisions", "ip")
    op.drop_column("approval_decisions", "payload_json")
    op.drop_column("approval_decisions", "approval_instance_step_id")
    op.drop_column("approval_decisions", "approval_instance_id")
