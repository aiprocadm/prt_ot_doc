"""SEC-65 FINAL: RLS on the auth path, tokens and infra queues.

Revision ID: 20260727_sec65_rls_auth_queues_final
Revises: 20260726_sec65_pre_final_constraints
Create Date: 2026-07-27

The last SEC-65 slice: 15 tables, taking coverage from 249 to 264 of 265 tenant
tables. One table stays exempt by design (``authz_permissions`` — see
``core/rls_policy.py``).

  * Authorisation (4) — authz_roles, authz_policies, authz_user_roles,
    authz_role_permissions.
  * Users (3) — "user", user_role, user_attribute.
  * Tokens & sessions (3) — api_key, api_tokens, refresh_session.
  * Infra queues (4) — outbox, outbox_events, idempotency_keys,
    inbound_webhook_dedup.
  * Webhooks (1) — webhook_subscription.

Prerequisites landed in ``20260726_sec65_pre_final_constraints`` + the fixes that
shipped with it: without them arming these tables would 500 every login
(refresh-session INSERT after an early commit), 500 every admin role/attribute
change, break API-key auth, and make idempotency replays fail. Do not
cherry-pick this migration without that change.

Two guards run before anything is armed, because both conditions are silent
failures rather than loud ones:

  1. ``webhook_subscription`` is the only table here whose ``tenant_id`` is
     NULLABLE, and the dispatcher has a legacy "global subscription" branch
     (``services/webhooks.py``). No application code writes such rows — the only
     writer in the repository is ``tests/test_webhook_routing.py``, which runs on
     SQLite where RLS is a no-op. A row inserted by hand would simply stop receiving
     events under the id-equality predicate, with delivery silently falling back to
     env URLs, so the guard turns that silence into a loud migration failure. The
     fallback branch itself becomes unreachable on PostgreSQL once this runs.
  2. ``webhook_subscriptions`` (PLURAL) is a shadow table created by
     ``20260314_next43_outbox_webhooks_spine.py`` with a tenant_id + FK but no ORM
     model, so the ratchet guard (which enumerates tenant tables from SQLAlchemy
     metadata) cannot see it and it is outside the 265 denominator. Arming it would
     break ``test_rls_enabled_matches_postgres`` (live-vs-registry equality) while
     registering it would trip the guard's "not a tenant table" check. It is empty
     and unreferenced, so it is dropped — otherwise "every tenant table is
     classified" stays false at the database level. If it ever holds rows, fail
     instead of destroying data.

No backfill: every table here has ``tenant_id NOT NULL`` with a FK to ``tenant.id``
(``outbox_events`` got both in the previous migration), so a slug can no longer be
stored, and ``webhook_subscription`` is empty.

Mechanism (see ``backend/app/db/session.py::_apply_tenant_rls``):
  - ``app.current_tenant`` — GUC pinned to the session tenant per transaction.
  - ``app.bypass_rls``      — ``'on'`` for trusted system/cross-tenant seeders/jobs.
Policy denies when neither is set (fail-closed). ``FORCE ROW LEVEL SECURITY`` makes
it apply even to the table owner — but NOT to a superuser: the application role must
be ``NOSUPERUSER NOBYPASSRLS`` for any of this to be enforced at runtime.
PostgreSQL-only.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260727_sec65_rls_auth_queues_final"
down_revision: str | Sequence[str] | None = "20260726_sec65_pre_final_constraints"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Sorted; matches the live-metadata set. "user" is a reserved word — every statement
# below quotes table names, so it needs no special casing.
_TABLES = (
    "api_key",
    "api_tokens",
    "authz_policies",
    "authz_role_permissions",
    "authz_roles",
    "authz_user_roles",
    "idempotency_keys",
    "inbound_webhook_dedup",
    "outbox",
    "outbox_events",
    "refresh_session",
    "user",
    "user_attribute",
    "user_role",
    "webhook_subscription",
)

_POLICY = "tenant_isolation"

_PREDICATE = (
    "current_setting('app.bypass_rls', true) = 'on' "
    "OR tenant_id = current_setting('app.current_tenant', true)"
)


def _guard_global_webhook_subscriptions(bind) -> None:
    orphans = bind.execute(
        sa.text("SELECT count(*) FROM webhook_subscription WHERE tenant_id IS NULL")
    ).scalar_one()
    if orphans:
        raise RuntimeError(
            f"webhook_subscription holds {orphans} global row(s) with tenant_id IS NULL. "
            "Under the tenant_isolation policy they would become invisible and their "
            "events would silently fall back to env-configured URLs. Convert them to "
            "per-tenant subscriptions (or delete them), then re-run this migration."
        )


def _drop_shadow_subscriptions_table(bind) -> None:
    exists = bind.execute(sa.text("SELECT to_regclass('public.webhook_subscriptions')")).scalar()
    if not exists:
        return
    rows = bind.execute(sa.text("SELECT count(*) FROM webhook_subscriptions")).scalar_one()
    if rows:
        raise RuntimeError(
            f"webhook_subscriptions (plural) unexpectedly holds {rows} row(s). It has no ORM "
            "model and no readers/writers, so it was scheduled for removal — inspect the data "
            "and drop it manually before re-running this migration."
        )
    op.execute("DROP TABLE webhook_subscriptions")


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    _guard_global_webhook_subscriptions(bind)
    _drop_shadow_subscriptions_table(bind)

    # ENABLE/FORCE take an ACCESS EXCLUSIVE lock on tables that every request touches
    # ("user", refresh_session, api_key). Without a bound, one long-running transaction
    # would park the ALTER at the head of the queue and stall all traffic behind it;
    # failing fast is the safer outcome — re-run the migration in a quieter window.
    op.execute("SET LOCAL lock_timeout = '5s'")

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

    # Recreate the shadow table (empty — the upgrade refuses to drop a populated one) so the
    # chain stays reversible: ``20260314_next43_outbox_webhooks_spine`` calls a plain
    # ``op.drop_table("webhook_subscriptions")`` in its own downgrade and would fail on a
    # missing table. Definition copied verbatim from that migration.
    if op.get_bind().dialect.has_table(op.get_bind(), "webhook_subscriptions"):
        return
    op.create_table(
        "webhook_subscriptions",
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("secret", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("event_types", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
