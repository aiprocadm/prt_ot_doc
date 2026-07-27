"""SEC-65 pre-final: legacy constraints + outbox_events tenant integrity.

Revision ID: 20260726_sec65_pre_final_constraints
Revises: 20260726_sec65_rls_audit_export_logs
Create Date: 2026-07-26

Groundwork for the last RLS slice (authz/user/token/queue tables). Nothing is armed
here — this migration only repairs schema-level defects that would otherwise surface
as "RLS broke it" once those tables get policies.

1. ``authz_roles``: drop the forgotten global ``UNIQUE (code)``.
   ``20260221_next9_authz_tables.py:29`` created it, ``20260313_next42_rbac_abac_audit.py:54``
   added the correct ``uq_authz_roles_tenant_code`` but never dropped the old one, and the
   ORM model does not declare it (so SQLite never had it). ``services/authz_seed.py`` looks a
   role up filtered by ``tenant_id``, so provisioning the SECOND tenant always INSERTs and
   dies on duplicate key — which ``platform_tenants.py`` then reports as
   409 "Tenant already exists". A pre-existing bug, but one that would land exactly inside
   the SEC-65 rollout window and be blamed on it.

2. ``outbox_events``: tenant integrity before the table can ever be armed.
   ``20260222_next10_job_engine.py:79-96`` created it WITHOUT a foreign key to ``tenant.id``
   (unlike outbox / idempotency_keys / inbound_webhook_dedup), so legacy rows may carry a
   tenant *slug* or *code* — invisible under an id-equality RLS predicate, i.e. events that
   stay PENDING forever with no error and no metric. We backfill those rows, then add the
   missing FK so the class of defect cannot come back.

3. ``outbox_events``: restore per-tenant uniqueness of ``event_id``.
   ``20260314_next43_outbox_webhooks_spine.py:30-31`` replaced
   ``uq_outbox_event_tenant_event (tenant_id, event_id)`` with a GLOBAL ``uq_outbox_event_event
   (event_id)``. Unique indexes are enforced above row security, so a global one leaks
   cross-tenant existence (insert fails for an id another tenant already used) and breaks
   ingestion of externally supplied event ids. Restored to ``(tenant_id, event_id)``, in sync
   with ``backend/app/models/job_engine.py``.

PostgreSQL-only; SQLite builds its schema from the ORM metadata.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260726_sec65_pre_final_constraints"
down_revision: str | Sequence[str] | None = "20260726_sec65_rls_audit_export_logs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_BACKFILL_OUTBOX_EVENTS = """
UPDATE outbox_events AS oe
SET tenant_id = t.id
FROM tenant AS t
WHERE oe.tenant_id <> t.id
  AND (oe.tenant_id = t.slug OR oe.tenant_id = t.code)
"""

# Rows whose tenant_id matches neither an id nor a slug/code cannot be healed
# automatically; fail loudly rather than let ADD CONSTRAINT abort with a bare
# ForeignKeyViolation the operator has to decode.
_ORPHAN_CHECK = """
SELECT count(*) FROM outbox_events oe
LEFT JOIN tenant t ON t.id = oe.tenant_id
WHERE t.id IS NULL
"""


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute("ALTER TABLE authz_roles DROP CONSTRAINT IF EXISTS authz_roles_code_key")

    op.execute(_BACKFILL_OUTBOX_EVENTS)
    orphans = bind.execute(sa.text(_ORPHAN_CHECK)).scalar_one()
    if orphans:
        raise RuntimeError(
            f"outbox_events: {orphans} row(s) reference a tenant that does not exist "
            "(tenant_id is neither an id nor a slug/code). Resolve them manually "
            "(delete or repoint), then re-run this migration."
        )
    op.execute(
        "ALTER TABLE outbox_events "
        "ADD CONSTRAINT fk_outbox_events_tenant "
        "FOREIGN KEY (tenant_id) REFERENCES tenant(id)"
    )

    op.execute("ALTER TABLE outbox_events DROP CONSTRAINT IF EXISTS uq_outbox_event_event")
    op.execute(
        "ALTER TABLE outbox_events "
        "ADD CONSTRAINT uq_outbox_event_tenant_event UNIQUE (tenant_id, event_id)"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute("ALTER TABLE outbox_events DROP CONSTRAINT IF EXISTS uq_outbox_event_tenant_event")
    op.execute("ALTER TABLE outbox_events ADD CONSTRAINT uq_outbox_event_event UNIQUE (event_id)")
    op.execute("ALTER TABLE outbox_events DROP CONSTRAINT IF EXISTS fk_outbox_events_tenant")
    # The legacy global UNIQUE (code) on authz_roles is deliberately NOT recreated:
    # it is the defect this migration removes, and re-adding it would fail on any
    # database that has since provisioned a second tenant.
