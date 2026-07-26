"""SEC-65: RLS second-line tenant isolation — notifications / calendar / client portal / NPA.

Revision ID: 20260726_sec65_rls_notifications_calendar_portal
Revises: 20260726_sec65_rls_approvals_edo_search
Create Date: 2026-07-26

Applies the proven RLS shape to 14 more tenant tables, taking coverage from 196
to 210 of 265 tenant tables:

  * Notifications (4) — notifications, notification_templates,
    notification_channel_settings, reminder_rules.
  * Calendar (3) — calendar_events, compliance_deadlines, saved_calendar_views.
  * Client portal (5) — client_portal_tokens, client_request_tickets,
    client_portal_read_models, portal_requests, portal_request_messages.
  * NPA (2) — legacy tenant-scoped npa, npabinding (the global reference lives in
    shared npa_act/npa_revision/npa_clause, out of scope).

Write-path analysis: every writer is either request-scoped (``get_session`` —
portal/notifications/calendar-views/compliance routes) or a tenant-pinned job
(``notifications.dispatch_pending`` beat → per-tenant ``session_scope(tenant=…)``;
``reminders.scan`` reads ``reminder_rules`` per tenant; outbox dispatch resolves
the tenant UUID before writing ``notifications``; portal projections rebuild under
``AsyncSessionLocal(tenant=…)``). Portal routes are middleware-public but every
handler resolves the tenant from ``X-Tenant`` via ``get_tenant_record`` before any
write. ``npa``/``npabinding``/``reminder_rules``/``calendar_events`` have no
production writers at all (read/schema-only). No dual-scope (slug in
``tenant_id``) usage exists for these tables — no backfill needed.

Fixed alongside this change (the commit-drops-GUCs hazard, see
``rearm_session_tenant_context``): ``commit()`` + ``refresh()`` handlers on
``saved_calendar_views`` (calendar_views.py), ``client_request_tickets``
(client_portal.py), ``portal_requests``/``portal_request_messages``
(modules/client_portal/api.py) — plus the same pre-existing pattern on
already-armed tables (``package_presets``/``package_runs`` in client_portal.py,
KPI reads after snapshot rebuild in modules/analytics/api.py).

Behavioral note: ``_portal_auth`` looks up ``client_portal_tokens`` without a
tenant filter; once armed, a token presented with a mismatched ``X-Tenant``
yields 401 (invalid token) instead of the previous 404 (run not found via the
already-armed ``package_runs``). Same rejection, earlier and cleaner.

Mechanism (see ``backend/app/db/session.py::_apply_tenant_rls``):
  - ``app.current_tenant`` — GUC pinned to the session tenant per transaction.
  - ``app.bypass_rls``      — ``'on'`` for trusted system/cross-tenant seeders/jobs.
Policy denies when neither is set (fail-closed). ``FORCE ROW LEVEL SECURITY`` makes
it apply even to the table owner. PostgreSQL-only.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20260726_sec65_rls_notifications_calendar_portal"
down_revision: str | Sequence[str] | None = "20260726_sec65_rls_approvals_edo_search"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Sorted; matches the live-metadata set. Legacy ``npa``/``npabinding`` have no underscore.
_TABLES = (
    "calendar_events",
    "client_portal_read_models",
    "client_portal_tokens",
    "client_request_tickets",
    "compliance_deadlines",
    "notification_channel_settings",
    "notification_templates",
    "notifications",
    "npa",
    "npabinding",
    "portal_request_messages",
    "portal_requests",
    "reminder_rules",
    "saved_calendar_views",
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
