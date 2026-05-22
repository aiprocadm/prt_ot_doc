"""Add custom risk methodology enum value (defensive — iter-15).

Revision ID: 20260318_next67_risk_custom_enum_hotfix
Revises: 20260318_next67
Create Date: 2026-03-18 18:30:00.000000

History:
* Original: emitted ``ALTER TYPE riskmethodologytype ADD VALUE IF NOT EXISTS
  'custom'`` unconditionally on Postgres. SQLite tolerated this because it
  has no enum type concept.
* iter-15 (CI run 26315758920, this branch): Postgres rejected the ALTER
  with ``UndefinedObjectError: type "riskmethodologytype" does not exist``.
  Investigation confirmed the type is never created in any migration —
  ``riskmethodology`` exists as a TABLE (see 20250322_risk_cards_action_plans),
  but no corresponding ENUM TYPE was ever materialized. The original hotfix
  was scaffolding for an enum design that never landed.
* Fix: wrap the ALTER in a defensive ``DO $$ IF EXISTS ... END $$`` block so
  the migration is a no-op when the type is absent (current state in this
  repo) and still extends the type cleanly if a future migration creates it.
  Preserves the DAG (next68 -> this -> next67) without requiring history
  rewrites.
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260318_next67_risk_custom_enum_hotfix"
down_revision = "20260318_next67"
branch_labels = None
depends_on = None


_GUARDED_ALTER_SQL = """
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'riskmethodologytype') THEN
        ALTER TYPE riskmethodologytype ADD VALUE IF NOT EXISTS 'custom';
    END IF;
END
$$;
"""


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(_GUARDED_ALTER_SQL)


def downgrade() -> None:
    # PostgreSQL enum values are not removed in-place safely.
    pass
