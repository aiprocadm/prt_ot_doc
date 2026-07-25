"""SEC-65: RLS second-line tenant isolation — OT operations (briefings/journals/permits/ops-inspections).

Revision ID: 20260725_sec65_rls_ot_ops
Revises: 20260724_sec65_rls_doc_pipeline
Create Date: 2026-07-25

Applies the proven RLS shape to 26 more tenant tables of the day-to-day
occupational-safety operations contour, taking coverage from 151 to 177 of 265
tenant tables:

  * Briefings (4) — briefing_templates/journals/entries/signatures.
  * Journals (3) — journal, journalentry, legacy plantask.
  * Work permits (6) — permit + work_permit/_member/_event/_briefing/_daily_admission.
  * Ops inspections & prescriptions (7) — ops_inspections, ops_prescriptions,
    prescription_items, regulatory_inspection, findings, attestation, checklist.
  * Corrective actions & tasks (6) — corrective_actions(+attachments), legacy
    correctiveaction, violation, task, plan_tasks.

Write-path analysis: every writer is either request-scoped (``get_session`` — briefings,
journals, safety_ops, tasks, attestations, work-permit/permit services) or a per-tenant
beat job (``reminders.scan`` → ``plan_tasks``, ``process_task_reminders`` → ``task``,
``permits.expiry.tick`` → ``permit`` — all inside ``session_scope(tenant=…)`` after a
Tenant-only enumeration on the default session). Demo seeding of briefings/work permits/
corrective actions already runs under ``rls_bypass=True``. Seven tables (checklist,
violation, correctiveaction, ops_inspections, prescription_items,
corrective_action_attachments, regulatory_inspection) are schema-only today. The one
latent hazard — ``OperationalDashboardService.get_dashboard``'s ``db is None`` fallback
opening a tenant-less ``SessionLocal()`` before querying ``task`` — is fixed in this
change by pinning ``SessionLocal(tenant_id=…)``; no other runtime code needed changes.

Mechanism (see ``backend/app/db/session.py::_apply_tenant_rls``):
  - ``app.current_tenant`` — GUC pinned to the session tenant per transaction.
  - ``app.bypass_rls``      — ``'on'`` for trusted system/cross-tenant seeders/jobs.
Policy denies when neither is set (fail-closed). ``FORCE ROW LEVEL SECURITY`` makes
it apply even to the table owner. PostgreSQL-only.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20260725_sec65_rls_ot_ops"
down_revision: str | Sequence[str] | None = "20260724_sec65_rls_doc_pipeline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Sorted; matches the live-metadata set. Legacy ``correctiveaction``/``journalentry``/
# ``plantask`` have no underscore.
_TABLES = (
    "attestation",
    "briefing_entries",
    "briefing_journals",
    "briefing_signatures",
    "briefing_templates",
    "checklist",
    "corrective_action_attachments",
    "corrective_actions",
    "correctiveaction",
    "findings",
    "journal",
    "journalentry",
    "ops_inspections",
    "ops_prescriptions",
    "permit",
    "plan_tasks",
    "plantask",
    "prescription_items",
    "regulatory_inspection",
    "task",
    "violation",
    "work_permit",
    "work_permit_briefing",
    "work_permit_daily_admission",
    "work_permit_event",
    "work_permit_member",
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
