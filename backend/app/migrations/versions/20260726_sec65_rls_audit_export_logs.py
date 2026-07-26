"""SEC-65: RLS second-line tenant isolation — audit / export / logs / presets.

Revision ID: 20260726_sec65_rls_audit_export_logs
Revises: 20260726_sec65_rls_finance_webhooks_kpi
Create Date: 2026-07-26

Applies the proven RLS shape to 17 more tenant tables, taking coverage from 226
to 243 of 265 tenant tables:

  * Audit (3) — auditlog, securityauditlog (no production writers today),
    audit_export_job.
  * Export center (2) — export_jobs, export_schedules (no beat tick scans the
    schedules — cron fields are API-written and never polled).
  * Logs / runs (3) — download_logs, job_logs (no writers at all),
    pdf_conversion_runs.
  * Field ops / offline (3) — external_registry_jobs, offline_media_queue,
    offline_sync_batches (no tenant-less queue polling exists).
  * Replace (2) — replace_map, replace_run.
  * Definitions / presets (4) — report_definition, featureenablement,
    header_footer_presets, marketplace_catalog_items.

All 17 carry an enforced ``FOREIGN KEY (tenant_id) REFERENCES tenant(id)``
(NOT NULL), so legacy slug rows cannot exist and no backfill is needed.

Write-path analysis: every writer is request-scoped (``get_session``) or a
tenant-pinned celery session (``session_scope(tenant=…)``); feature flags are
read via route dependencies on the request session (nothing middleware-level),
and ``apply_plan`` writes the *target* tenant's flags on a target-bound session.
Demo seeding (featureenablement, report_definition) already runs under
``rls_bypass=True``. Hazards fixed alongside this change: the ``@audit_operation``
decorator (and two direct ``AuditService`` call sites) writes the audit row
*after* the handler's ``commit()`` dropped the GUCs — it now re-arms first, for
all ~76 decorated handlers; the audit hash chain is now explicitly per-tenant
(``_prev_hash`` filter + tenant-keyed advisory lock) so RLS visibility and chain
semantics agree on both backends; ``report_export_job``'s failure branch re-arms
after ``rollback()`` (else failed jobs would stick in ``queued`` forever);
``commit()``+``refresh()`` handlers in replace/report-builder/headers re-arm
before the refresh; the platform fleet/provisioning handlers re-arm after commit
(latent until their tables get RLS).

Mechanism (see ``backend/app/db/session.py::_apply_tenant_rls``):
  - ``app.current_tenant`` — GUC pinned to the session tenant per transaction.
  - ``app.bypass_rls``      — ``'on'`` for trusted system/cross-tenant seeders/jobs.
Policy denies when neither is set (fail-closed). ``FORCE ROW LEVEL SECURITY`` makes
it apply even to the table owner. PostgreSQL-only.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20260726_sec65_rls_audit_export_logs"
down_revision: str | Sequence[str] | None = "20260726_sec65_rls_billing_tenant_admin"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Sorted; matches the live-metadata set.
_TABLES = (
    "audit_export_job",
    "auditlog",
    "download_logs",
    "export_jobs",
    "export_schedules",
    "external_registry_jobs",
    "featureenablement",
    "header_footer_presets",
    "job_logs",
    "marketplace_catalog_items",
    "offline_media_queue",
    "offline_sync_batches",
    "pdf_conversion_runs",
    "replace_map",
    "replace_run",
    "report_definition",
    "securityauditlog",
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
