"""SEC-65: RLS second-line tenant isolation — extend to the documents domain.

Revision ID: 20260722_sec65_rls_documents
Revises: 20260722_sec65_rls_ppe
Create Date: 2026-07-22

Applies the proven RLS shape to the 11 core document tables (documents, versions,
snapshots, artifacts, generation jobs/steps, batch runs, packs). Documents are the
most sensitive tenant data on the platform, so a DB-enforced second isolation line
is especially valuable here.

Scope note: ``contractor_document*`` (contractors domain) and ``search_documents``
(cross-entity search index) are intentionally left to their own slices. All write
paths to the tables below are tenant-scoped — request handlers and Celery jobs open
``session_scope(tenant=…)`` / ``AsyncSessionLocal(tenant=…)``; there is no global,
tenant-less queue poll over these job tables — so FORCE RLS does not starve the
document-generation worker.

Mechanism (see ``backend/app/db/session.py::_apply_tenant_rls``):
  - ``app.current_tenant`` — GUC pinned to the session tenant per transaction.
  - ``app.bypass_rls``      — ``'on'`` for trusted system/cross-tenant seeders/jobs.
Policy denies when neither is set (fail-closed). ``FORCE ROW LEVEL SECURITY`` makes
it apply even to the table owner. PostgreSQL-only.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20260722_sec65_rls_documents"
down_revision: str | Sequence[str] | None = "20260722_sec65_rls_ppe"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = (
    "document",
    "documentversion",
    "document_snapshot",
    "document_artifacts",
    "document_batch_run",
    "document_batch_item",
    "document_jobs",
    "document_job_steps",
    "document_pack",
    "document_pack_item",
    "documentgenerationjob",
)

_POLICY = "tenant_isolation"

_PREDICATE = (
    "current_setting('app.bypass_rls', true) = 'on' "
    "OR tenant_id = current_setting('app.current_tenant', true)"
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    for table in _TABLES:
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
        op.execute(
            f'CREATE POLICY "{_POLICY}" ON "{table}" '
            f"FOR ALL USING ({_PREDICATE}) WITH CHECK ({_PREDICATE})"
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    for table in reversed(_TABLES):
        op.execute(f'DROP POLICY IF EXISTS "{_POLICY}" ON "{table}"')
        op.execute(f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')
