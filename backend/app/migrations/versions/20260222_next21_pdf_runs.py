"""next21 pdf conversion runs (iter-15e: file_versions removed — stale duplicate)

Revision ID: 20260222_next21
Revises: 20260223_next15
Create Date: 2026-02-22

History:
* Originally created both ``file_versions`` AND ``pdf_conversion_runs``.
* iter-15e (CI run 26316247156): the ``file_versions`` block here conflicted
  with the canonical ``file_versions`` schema created by
  ``20260302_next29_files_search_v1`` on a sibling DAG branch. Both branches
  are reachable from ``20260416_next69_merge_heads``, so at upgrade-head
  Postgres saw two ``create_table("file_versions", ...)`` calls with
  incompatible columns. SQLite tolerated this via
  ``__table_args__ = {"extend_existing": True}`` in the dead-code
  ``backend/app/modules/pdf/models.py:FileVersion``, masking the bug.
* Investigation confirmed: schema B (next29) is canonical. The live
  application (``files/api.py``, ``files/service.py``, ``next35`` trgm
  index on ``filename``) targets next29's columns. Schema A
  (object_key/app_version/FK->file.id) is referenced by ZERO code paths.
* Fix: remove ``file_versions`` create_table + its indexes from this
  revision's upgrade and from downgrade. ``pdf_conversion_runs`` (used
  by ``modules/pdf/api.py``, ``modules/pdf/repo.py``, ``tasks/_core.py``)
  stays. Dead-code ``modules/pdf/models.py:FileVersion`` and its
  registration in ``db/base.py`` are removed in the same commit.
"""

import sqlalchemy as sa
from alembic import op

revision = "20260222_next21"
down_revision = "20260223_next15"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pdf_conversion_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("input_file_id", sa.String(length=36), nullable=False),
        sa.Column("output_file_id", sa.String(length=36), nullable=True),
        sa.Column("source_document_version_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="queued"),
        sa.Column("timeout_s", sa.Integer(), nullable=False, server_default="45"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_payload", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("correlation_id", sa.String(length=128), nullable=True),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["input_file_id"], ["file.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["output_file_id"], ["file.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_pdf_runs_tenant_status", "pdf_conversion_runs", ["tenant_id", "status"])
    op.create_index("ix_pdf_runs_input", "pdf_conversion_runs", ["tenant_id", "input_file_id"])


def downgrade() -> None:
    op.drop_index("ix_pdf_runs_input", table_name="pdf_conversion_runs")
    op.drop_index("ix_pdf_runs_tenant_status", table_name="pdf_conversion_runs")
    op.drop_table("pdf_conversion_runs")
    # iter-15e: file_versions block removed from upgrade — no corresponding
    # drop here. next29 (sibling branch) is the sole creator now and owns
    # the canonical downgrade for that table.
