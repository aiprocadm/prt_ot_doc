"""SEC-65: RLS second-line tenant isolation — СОУТ, risks, contractors, budget.

Revision ID: 20260723_sec65_rls_sout_risk_contractors_budget
Revises: 20260723_sec66_pdn_access_log
Create Date: 2026-07-23

Applies the proven RLS shape to 37 more tenant tables across four domains. With the
SEC-66 ``pdn_access_log`` table (merged just before this slice) also armed, the
registry ends at 73 enabled / 192 exempt / 265 tenant tables:

  * СОУТ (5) — assessment campaigns, workplaces, factors, guarantees, class history.
  * Risks (21) — risk register, assessments, cards, controls, matrices, maps, the
    legacy ``riskmap``/``riskmethodology`` pair, hazards + bindings/measures,
    workplace/position hazard links, and corrective action plans.
  * Contractors (6) — registry, employees, documents + requirements, incidents and
    the readiness read model.
  * Budget (5) — safety budget, expense articles/expenses, СФР reimbursements + items.

Write-path analysis (the check that matters before FORCE RLS): every writer to these
tables is tenant-scoped. Request handlers get their session from
``api/dependencies.py::get_session``, which passes ``tenant_id=str(tenant.id)`` so the
``app.current_tenant`` GUC is always pinned. The contractor ticks
(``tasks/domain_ticks.py``) and the projection jobs (``celery/tasks/projections_jobs.py``,
the only writer of ``contractor_readiness_read_models``) loop one tenant at a time and
open ``session_scope(tenant=…)`` / ``AsyncSessionLocal(tenant=<uuid>)``. There is no
tenant-less queue poll or raw-engine writer over any of these tables, and the demo
seeder already runs with ``rls_bypass=True``. So FORCE RLS starves nothing.

Scope note: ``workplace``, ``position`` and the rest of the org-structure registry are
deliberately left out — they are a shared backbone for several domains and get their
own slice. ``search_documents`` (cross-entity index) likewise.

Mechanism (see ``backend/app/db/session.py::_apply_tenant_rls``):
  - ``app.current_tenant`` — GUC pinned to the session tenant per transaction.
  - ``app.bypass_rls``      — ``'on'`` for trusted system/cross-tenant seeders/jobs.
Policy denies when neither is set (fail-closed). ``FORCE ROW LEVEL SECURITY`` makes
it apply even to the table owner. PostgreSQL-only.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20260723_sec65_rls_sout_risk_contractors_budget"
down_revision: str | Sequence[str] | None = "20260723_sec66_pdn_access_log"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Names taken from live SQLAlchemy metadata, not from grepping model classes: the
# legacy ``riskmap``/``riskmethodology`` tables have no underscore and would be missed
# (same trap as the ``ppenorm``/``ppeitem``/``ppeissue`` trio in the СИЗ slice).
_TABLES = (
    # СОУТ
    "sout_campaign",
    "sout_workplace",
    "sout_factor",
    "sout_guarantee",
    "sout_class_history",
    # Risks
    "risk",
    "risk_assessments",
    "risk_assessment_items",
    "risk_cards",
    "risk_controls",
    "risk_hazards",
    "risk_matrix",
    "risk_measures",
    "risk_methodologies",
    "risk_maps",
    "risk_map_items",
    "risk_map_item_measures",
    "riskmap",
    "riskmethodology",
    "hazards",
    "hazard_measures",
    "hazard_bindings",
    "workplace_hazard",
    "position_hazard",
    "action_plans",
    "action_plan_items",
    # Contractors
    "contractor_registry",
    "contractor_employees",
    "contractor_documents",
    "contractor_document_requirement",
    "contractor_incidents",
    "contractor_readiness_read_models",
    # Budget
    "safety_budget",
    "budget_expense_article",
    "budget_expense",
    "budget_reimbursement",
    "budget_reimbursement_item",
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
