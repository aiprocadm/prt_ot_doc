"""SEC-65: RLS second-line tenant isolation — approvals / EDO / search / signatures.

Revision ID: 20260726_sec65_rls_approvals_edo_search
Revises: 20260725_sec65_rls_ot_ops
Create Date: 2026-07-26

Applies the proven RLS shape to 19 more tenant tables of the approval/EDO/search
contour, taking coverage from 177 to 196 of 265 tenant tables:

  * Approvals (9) — approval_routes/_route_steps/_requests/_decisions/_decision_logs,
    approval_processes/_tasks (signing v1), approval_instances/_instance_steps.
  * EDO (5) — edo_messages, edo_receipts, edo_status_events, edo_status_history,
    edo_webhook_inbox.
  * Search (4) — search_documents, search_index_entries, search_recent_queries,
    search_saved_queries.
  * Signatures (1) — signature_requests.

Write-path analysis: every writer is either request-scoped (``get_session`` —
approval_orchestration, approval_signing_v1, edo_workflow, pep_signing, search,
files upload indexing) or a tenant-pinned celery job (``process_inbound_webhook``
→ ``session_scope(tenant=slug)`` writes ``edo_status_history``;
``reindex_search_entity_job`` → ``AsyncSessionLocal(tenant=id)`` writes
``search_index_entries``; ``files.index_content`` → ``session_scope(tenant=slug)``
writes ``search_documents``). Inbound EDO webhooks resolve the tenant *before* any
insert (``_preload_webhook_tenant`` middleware / mandatory ``X-Tenant``), so
``edo_webhook_inbox`` is only written under a tenant session. Provisioning seeds
none of these tables; the escalation/EDO-retry beat jobs are DB-less stubs.
``edo_receipts`` is schema-only today. Two hazards fixed alongside this change:

  * ``modules/search/api.py`` degraded path rolled back (dropping the
    transaction-local GUCs) and then INSERTed into ``search_recent_queries`` —
    now re-arms the tenant context first (``rearm_session_tenant_context``).
  * ``edo_messages`` predates the tenant FK and its consumer tolerates legacy
    rows whose ``tenant_id`` holds the tenant *slug/code* (``tasks/_core.py``
    dual-scope lookup). The policy compares against the tenant *id*, which would
    silently hide such rows — this migration backfills them to ``tenant.id``
    before arming the table.

Mechanism (see ``backend/app/db/session.py::_apply_tenant_rls``):
  - ``app.current_tenant`` — GUC pinned to the session tenant per transaction.
  - ``app.bypass_rls``      — ``'on'`` for trusted system/cross-tenant seeders/jobs.
Policy denies when neither is set (fail-closed). ``FORCE ROW LEVEL SECURITY`` makes
it apply even to the table owner. PostgreSQL-only.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20260726_sec65_rls_approvals_edo_search"
down_revision: str | Sequence[str] | None = "20260725_sec65_rls_ot_ops"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Sorted; matches the live-metadata set.
_TABLES = (
    "approval_decision_logs",
    "approval_decisions",
    "approval_instance_steps",
    "approval_instances",
    "approval_processes",
    "approval_requests",
    "approval_route_steps",
    "approval_routes",
    "approval_tasks",
    "edo_messages",
    "edo_receipts",
    "edo_status_events",
    "edo_status_history",
    "edo_webhook_inbox",
    "search_documents",
    "search_index_entries",
    "search_recent_queries",
    "search_saved_queries",
    "signature_requests",
)

_POLICY = "tenant_isolation"

_PREDICATE = (
    "current_setting('app.bypass_rls', true) = 'on' "
    "OR tenant_id = current_setting('app.current_tenant', true)"
)

# ``edo_messages`` was created without a tenant FK and legacy rows may carry the
# tenant slug/code in ``tenant_id`` (tolerated by the dual-scope lookup in
# ``tasks/_core.py::process_inbound_webhook``). The RLS predicate matches the
# tenant *id* only, so heal such rows before arming the table.
_BACKFILL_EDO_TENANT_ID = """
UPDATE edo_messages AS em
SET tenant_id = t.id
FROM tenant AS t
WHERE em.tenant_id <> t.id
  AND (em.tenant_id = t.slug OR em.tenant_id = t.code)
"""


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(_BACKFILL_EDO_TENANT_ID)
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
