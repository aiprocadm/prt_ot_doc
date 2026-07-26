"""SEC-65: RLS second-line tenant isolation — finance / webhooks / KPI read-models / automation.

Revision ID: 20260726_sec65_rls_finance_webhooks_kpi
Revises: 20260726_sec65_rls_notifications_calendar_portal
Create Date: 2026-07-26

Applies the proven RLS shape to 16 more tenant tables, taking coverage from 210
to 226 of 265 tenant tables:

  * Finance (4) — contract, order, invoice, invoices (BillingInvoice is read-only
    in code today).
  * Billing telemetry (4) — billing_events, tenant_counters,
    tenant_quotas_counters, tenant_rate_limits (the latter has no code paths at
    all beyond its model/migration).
  * Read-models / KPI (4) — dashboard_kpi_snapshots, kpi_definitions,
    person_compliance_read_models, site_safety_read_models.
  * Webhooks (2) — webhook_endpoints, webhook_deliveries (both carry an enforced
    ``FOREIGN KEY (tenant_id) REFERENCES tenant(id)``, so no legacy slug rows can
    exist and no backfill is needed — unlike ``edo_messages``).
  * Automation (2) — automation_rule, automation_rule_trigger.

Deliberately NOT in this slice (recorded in ``core/rls_policy.py``):
``usage_counters``/``subscriptions``/``tenant_limits_override``/
``tenant_integrations_keys`` are read (and usage rows created) by
``BillingGuardMiddleware`` on a tenant-less ``AsyncSessionLocal(tenant="public")``
before the tenant middleware runs — arming them would 500 every request
(usage-row insert) or silently fail-open the billing gate; the guard needs a
dedicated rework first. ``tenant_quotas``/``tenant_settings`` are managed
cross-tenant by the platform fleet endpoints on the caller's session.
``webhook_subscription`` legitimately stores global rows with ``tenant_id IS
NULL`` which the id-equality predicate would hide.

Write-path analysis for the armed 16: finance/webhook-endpoint/KPI writers are
request-scoped (``get_session``); quota counters are written via ``assert_quota``
on the request session; projection rebuilds run on tenant-pinned celery sessions
with a single trailing commit; the rules engine evaluates synchronously on the
caller's tenant session. The outbox webhook dispatcher runs in
``session_scope(tenant=…)`` — two hazards fixed alongside this change:
``services/outbox.py::process_once`` committed mid-loop (dropping the GUCs) before
the delivery bookkeeping (now re-arms), and ``tasks/_core.py`` stamped
``WebhookDelivery.tenant_id`` from the outbox event — ``outbox_events`` has no
tenant FK, so legacy events may carry a slug, which the deliveries FK (and now
the RLS WITH CHECK) rejects — it now uses the resolved tenant UUID. ``commit()``+``refresh()`` handlers on
contracts/orders/invoices/webhooks/public_api/export_center now re-arm before the
refresh. ``scripts/create_tenant.py`` provisioning session now runs with
``rls_bypass=True`` like the other two provisioning paths.

Mechanism (see ``backend/app/db/session.py::_apply_tenant_rls``):
  - ``app.current_tenant`` — GUC pinned to the session tenant per transaction.
  - ``app.bypass_rls``      — ``'on'`` for trusted system/cross-tenant seeders/jobs.
Policy denies when neither is set (fail-closed). ``FORCE ROW LEVEL SECURITY`` makes
it apply even to the table owner. PostgreSQL-only.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20260726_sec65_rls_finance_webhooks_kpi"
down_revision: str | Sequence[str] | None = "20260726_sec65_rls_notifications_calendar_portal"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Sorted; matches the live-metadata set.
_TABLES = (
    "automation_rule",
    "automation_rule_trigger",
    "billing_events",
    "contract",
    "dashboard_kpi_snapshots",
    "invoice",
    "invoices",
    "kpi_definitions",
    "order",
    "person_compliance_read_models",
    "site_safety_read_models",
    "tenant_counters",
    "tenant_quotas_counters",
    "tenant_rate_limits",
    "webhook_deliveries",
    "webhook_endpoints",
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
