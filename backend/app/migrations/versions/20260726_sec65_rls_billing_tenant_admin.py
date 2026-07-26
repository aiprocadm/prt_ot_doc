"""SEC-65: RLS second-line tenant isolation — billing gate & tenant admin tables.

Revision ID: 20260726_sec65_rls_billing_tenant_admin
Revises: 20260726_sec65_rls_finance_webhooks_kpi
Create Date: 2026-07-26

Arms the 6 tables that were deliberately deferred by the previous slice because
hot-path/platform code touched them on tenant-less sessions, taking coverage
from 226 to 232 of 265 tenant tables:

  * Billing gate (4) — usage_counters, subscriptions, tenant_limits_override,
    tenant_integrations_keys.
  * Tenant admin (2) — tenant_quotas, tenant_settings.

The enabling rework ships in this change:

  * ``BillingGuardMiddleware`` now opens its per-request session pinned to the
    request tenant (``AsyncSessionLocal(tenant=<slug>)`` — slug resolved to the
    UUID GUC on enter) instead of ``tenant="public"``. The gate's subscription/
    override/usage reads and its usage-row flush therefore match the RLS
    predicate. Least-privilege: no bypass on the hot path.
  * ``TenantMiddleware`` reads ``tenant_settings``/``tenant_quotas`` after
    resolving the tenant — its lookup session is now pinned to that tenant
    (previously tenant-less → under RLS the settings would silently read as
    ``None`` and schema/S3-prefix fell back to the ``tenant`` row).
  * Fleet endpoints (``api/routes/platform_tenants.py``) read/write OTHER
    tenants' quotas; they now run those reads/writes on a trusted
    ``rls_bypass`` shared-schema session (``_fleet_session``), authorised by
    ``_require_managing_admin``. ``apply_plan`` receives that session for the
    quota half of a plan switch.
  * ``api/routes/tenants.py::create_tenant_endpoint`` provisioned
    ``tenant_settings``/``tenant_quotas`` for the NEW tenant on the caller's
    request session — now uses an ``rls_bypass`` provisioning session like
    ``platform_tenants``/``bootstrap_tenant``/``create_tenant.py`` do.

Writers were verified exhaustively: billing routes and ``add_usage`` write on
the request session with the tenant's own id; ``BootstrapTenantService`` and all
three provisioning paths run under ``rls_bypass``; ``integration_readiness``
reads its own tenant's keys on the request session. Every writer has always
stamped ``tenant_id`` with the tenant UUID (never the slug), so no backfill is
needed.

Still exempt after this slice (see ``core/rls_policy.py``): auth hot path
(``authz_*``, ``api_key``/``api_tokens``/``refresh_session``/``user*``),
``webhook_subscription`` (legitimate global rows with ``tenant_id IS NULL``),
cross-tenant infra queues (``outbox*``, ``idempotency_keys``,
``inbound_webhook_dedup``) and the audit/export/logs group.

Mechanism (see ``backend/app/db/session.py::_apply_tenant_rls``):
  - ``app.current_tenant`` — GUC pinned to the session tenant per transaction.
  - ``app.bypass_rls``      — ``'on'`` for trusted system/cross-tenant seeders/jobs.
Policy denies when neither is set (fail-closed). ``FORCE ROW LEVEL SECURITY`` makes
it apply even to the table owner. PostgreSQL-only.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20260726_sec65_rls_billing_tenant_admin"
down_revision: str | Sequence[str] | None = "20260726_sec65_rls_finance_webhooks_kpi"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Sorted; matches the live-metadata set.
_TABLES = (
    "subscriptions",
    "tenant_integrations_keys",
    "tenant_limits_override",
    "tenant_quotas",
    "tenant_settings",
    "usage_counters",
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
