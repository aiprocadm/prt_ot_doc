"""iter-21: add user.company_id column missing from initial schema.

Revision ID: 20260527_iter21_user_company_id
Revises: 20260517_saved_calendar_views
Create Date: 2026-05-27

History:
* iter-21 first attempt pointed ``down_revision`` at
  ``20260416_next69_merge_heads`` (the merge revision documented in that
  file's docstring as "the merge"). That was wrong: ``20260517_saved_
  calendar_views`` had since been added chained off next69, making next69
  no longer a head. Pointing iter-21 at next69 created a parallel branch
  → ``Multiple head revisions are present`` on ``alembic upgrade head``
  (PR #589 first CI run). Fixed by repointing to the actual head. Lesson:
  always verify true head with ``alembic heads`` or ``grep -rl down_
  revision.*<candidate>`` to confirm nothing else chains off it.

Root cause: `User.company_id` was added to `backend/app/models/models.py`
(commit 0d4d140 "Harden refresh token handling with cookie rotation and
revocation") without a paired Alembic migration. `6b6dee7c951f_initial_schema.py:
365-380` creates the `user` table with no `company_id` column, and no
subsequent migration adds it. SQLite-backed unit tests pass because
`Base.metadata.create_all()` builds the schema directly from the model,
but PG-backed perf-smoke fails at api-1 startup when `bootstrap_admin_user`
issues `SELECT ... FROM user LEFT JOIN company ON company.id = user.company_id`
with `asyncpg.exceptions.UndefinedColumnError: column user.company_id does
not exist`. The `alembic-postgres-upgrade` CI job didn't surface the drift
because it never executes ORM queries.

This migration:
1. Adds nullable `company_id String(36)` to `user`.
2. Creates `fk_user_company` FK to `company.id` with `ON DELETE SET NULL`
   (matches `ForeignKey("company.id", ondelete="SET NULL")` on the model).
3. Creates `ix_user_company` composite index on `(tenant_id, company_id)`
   (matches `__table_args__` on the model).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260527_iter21_user_company_id"
down_revision: str | Sequence[str] | None = "20260517_saved_calendar_views"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("user", sa.Column("company_id", sa.String(length=36), nullable=True))
    op.create_foreign_key(
        "fk_user_company",
        "user",
        "company",
        ["company_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_user_company",
        "user",
        ["tenant_id", "company_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_user_company", table_name="user")
    op.drop_constraint("fk_user_company", "user", type_="foreignkey")
    op.drop_column("user", "company_id")
