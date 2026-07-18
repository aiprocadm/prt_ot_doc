"""NEXT-55b templates lifecycle data — no-op (iter-14)

Revision ID: 20260328_next55b
Revises: 20260328_next55
Create Date: 2026-05-22

History:
* iter-12/13 introduced this revision to backfill ``templateversion.status``
  to ``'UPLOADED'`` after the original next55 was rewritten from a
  drop-and-recreate pattern (which would have NULL'd the column) to an
  ALTER TYPE ADD VALUE pattern (which preserves existing values).
* iter-13 split the UPDATE into a separate revision believing PG12+'s
  catalog-visibility constraint ("new enum values must be committed before
  use") would be satisfied by alembic's transaction-per-revision semantics.
  CI run 26294051531 proved this assumption wrong: env.py wraps the entire
  ``alembic upgrade head`` in one outer ``connectable.begin()`` async
  transaction, so all revisions share one tx. The UPDATE failed with
  ``UnsafeNewEnumValueUsageError``.
* iter-14 removes the UPDATE entirely. Rationale: with ALTER TYPE ADD VALUE
  preserving existing column values, the legacy {DRAFT, ACTIVE, ARCHIVED}
  states remain valid in the extended enum {DRAFT, ACTIVE, ARCHIVED,
  UPLOADED, LINTED, READY, DEPRECATED}. The UPDATE was a leftover from the
  original drop-and-recreate workaround and is now both lossy (collapses
  three meaningful states into one) and structurally impossible inside
  alembic's outer transaction. Application code already handles the legacy
  values; only new templateversion rows write the new lifecycle values.

The revision file itself is kept (not deleted) because next56's
``down_revision`` points at next55b. Emptying the upgrade is the smallest-
diff fix that preserves the DAG.

Future follow-up: if a data backfill is required, run it as a startup hook
or one-shot CLI command (``app.cli.main``) after ``alembic upgrade head``
completes — that is the only safe place to use newly-added enum values
without refactoring env.py's outer-transaction wrapper.
"""

from alembic import op  # noqa: F401  -- kept for parity / future use

revision = "20260328_next55b"
down_revision = "20260328_next55"
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
