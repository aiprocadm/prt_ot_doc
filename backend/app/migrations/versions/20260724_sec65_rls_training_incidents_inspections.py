"""SEC-65: RLS second-line tenant isolation — training, incidents, inspections.

Revision ID: 20260724_sec65_rls_training_incidents_inspections
Revises: 20260724_sec65_rls_org_registry
Create Date: 2026-07-24

Applies the proven RLS shape to 35 more tenant tables across three domains, taking
coverage from 82 to 117 of 265 tenant tables:

  * Training / LMS (15) — courses, programs, modules, lessons, tests + questions,
    attempts, enrollments, groups, sessions, plans, protocols + items, certificates.
  * Incidents (7) — incident, cases, investigations, log, attachments, person links.
  * Inspections (13) — inspection, runs + items, results, checklists + items, plans +
    items, prep packages/items/gaps, prescriptions, attachments.

Write-path analysis (all writers tenant-scoped): request handlers get their session
from ``api/dependencies.py::get_session`` (``app.current_tenant`` pinned); the domain
writers ``modules/incidents/operations.py`` (Incident/Inspection/InspectionResult) and
the training APIs open no session of their own — they use the caller's tenant session.
Background jobs (``tasks/notification_jobs.py``, ``tasks/_core.py``) use the same
list-tenants-then-per-tenant pattern as ``domain_ticks``: the default-tenant session
only enumerates the ``Tenant`` table; all domain reads/writes happen inside
``session_scope(tenant=…)``. The demo seeder seeds ``training_course`` under
``rls_bypass=True``; ``dev_bootstrap`` touches none of these tables. No tenant-less
(``tenant=None``) or raw-engine writer over these tables exists, so FORCE RLS starves
nothing.

Scope note: ``ops_inspections`` / ``ops_prescriptions`` / ``regulatory_inspection``
(the separate ops-inspections domain) are intentionally left to their own slice.

Mechanism (see ``backend/app/db/session.py::_apply_tenant_rls``):
  - ``app.current_tenant`` — GUC pinned to the session tenant per transaction.
  - ``app.bypass_rls``      — ``'on'`` for trusted system/cross-tenant seeders/jobs.
Policy denies when neither is set (fail-closed). ``FORCE ROW LEVEL SECURITY`` makes
it apply even to the table owner. PostgreSQL-only.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20260724_sec65_rls_training_incidents_inspections"
down_revision: str | Sequence[str] | None = "20260724_sec65_rls_org_registry"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = (
    # Training / LMS
    "training",
    "training_course",
    "training_programs",
    "training_modules",
    "training_lessons",
    "training_tests",
    "training_test_questions",
    "training_attempts",
    "training_enrollments",
    "training_groups",
    "training_session",
    "training_plan",
    "training_protocols",
    "training_protocol_items",
    "training_certificates",
    # Incidents
    "incident",
    "incident_cases",
    "incident_investigations",
    "incident_log",
    "incident_attachments",
    "incident_person",
    "incident_persons",
    # Inspections
    "inspection",
    "inspection_runs",
    "inspection_run_items",
    "inspection_result",
    "inspection_checklists",
    "inspection_checklist_items",
    "inspection_plans",
    "inspection_plan_items",
    "inspection_prep_packages",
    "inspection_prep_items",
    "inspection_prep_gaps",
    "inspection_prescription",
    "inspection_attachments",
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
