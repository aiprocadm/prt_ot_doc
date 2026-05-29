"""iter-48: outbox_events model-col closure.

Closes the LAST ``column_drift_lite`` business-drift table (Session 96
candidate). The ``OutboxEvent`` model (``backend/app/models/job_engine.py``)
declares one column no migration ever creates::

    last_error    Text    nullable

The table is born in ``20260222_next10`` (event_type, event_id, payload,
status, attempts, next_attempt_at + base) and extended by
``20260314_next43_outbox_webhooks_spine`` (aggregate_type, aggregate_id,
headers, sent_at). Neither adds ``last_error`` — yet it is live read/written:
the outbox delivery path records the failure reason there and the admin
diagnostics route surfaces it. On PostgreSQL (the ``alembic upgrade`` path)
those raise ``UndefinedColumnError``. So this is real drift, not a rename or
intentional design — iter-48 adds the column to match the model.

(The older *singular* ``outbox`` table carries its own ``last_error`` from
``20250305_add_outbox_delivery_metadata`` — a DISTINCT legacy table. This
migration concerns only the plural ``outbox_events``.)

Simplest variant in the whole drift cohort — a single NULLABLE ``Text``
column — so, unlike iter-47/iter-42, there is:
  * NO ``server_default``: a nullable column never violates a constraint on
    existing rows, so existing rows are satisfied by NULL (no backfill, zero
    data risk — contrast iter-35's NOT NULL ``riskmap.company_id``).
  * NO enum type: plain ``sa.Text()``, so no ``CREATE TYPE`` and no RB-002
    uppercase-label guard.
  * NO index: the model declares none on ``last_error``.

Ordering: ``outbox_events`` is created by ``20260222_next10``, which sits on
the main ``next`` backbone (next10 -> ... -> next43 -> ... -> next50) that
``20260416_next69_merge_heads`` collapses into a single ancestor of the entire
``iter`` cohort. So ``next10`` is a verified ancestor of ``iter38``; there are
no cross-branch FK targets (``last_error`` is a plain ``Text``). Hence
``down_revision = iter38`` alone orders this correctly under ``alembic upgrade
heads`` — like iter-47, no ``depends_on`` is needed.

After iter-48 lands, ``column_drift_lite`` business-drift drops from 1 -> 0
tables (critical already 0) — the capstone of the ORM<->migration drift
defect class.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260529_iter48_outbox_events_last_error"
down_revision: str | Sequence[str] | None = "20260529_iter38_server_default_c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # outbox_events.last_error — nullable Text, no default, no index (mirror of
    # the model declaration). Existing rows take NULL.
    op.add_column(
        "outbox_events",
        sa.Column("last_error", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("outbox_events", "last_error")
