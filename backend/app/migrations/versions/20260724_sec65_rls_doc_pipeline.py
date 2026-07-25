"""SEC-65: RLS second-line tenant isolation — document pipeline (files/packs/templates/workflow).

Revision ID: 20260724_sec65_rls_doc_pipeline
Revises: 20260724_sec65_rls_training_incidents_inspections
Create Date: 2026-07-24

Applies the proven RLS shape to 34 more tenant tables of the document-processing
pipeline, taking coverage from 117 to 151 of 265 tenant tables:

  * Files (9) — file/files, file_objects, file_versions, file_links, download logs,
    scan results, content/text indexes.
  * Packages (14) — pack_runs + items/logs, package_runs/events/requirements,
    presets/preset_items/presets_v2, profiles/profiles_v2, read models, and the legacy
    ``packagepreset``/``packageprofile`` pair.
  * Pipeline (3) — pipeline_profiles, pipeline_runs, pipeline_step_locks.
  * Templates (3) — template, templateversion, templateusage.
  * Workflow (5) — definitions + versions, instances, tasks, timeline events.

Write-path analysis (this domain is heavily background-processed — checked carefully):
every celery task over these tables opens ``session_scope(tenant=…)`` /
``AsyncSessionLocal(tenant=…)`` (``celery/tasks/pipeline_run.py``, ``tasks/file_jobs.py``,
``tasks/document_jobs.py``, ``celery/tasks/report_export_job.py``,
``celery/tasks/document_jobs_required.py``). ``pipeline_step_locks`` is written by
``pipelines_orchestrator`` with ``tenant_id=job.tenant_id`` inside the job's tenant
session. The tick/reminder jobs (``tasks/_core.py``) only read ``Tenant`` on the
default-tenant session and then do per-tenant work in ``session_scope(tenant=…)`` —
no global queue poll over these tables exists. The one provisioning-context writer
(``BootstrapTenantService._seed_package_presets`` → ``PackageProfile``) already runs on
the ``rls_bypass=True`` provisioning session (added in the org-registry slice). Demo and
dev bootstrap do not seed these tables. So FORCE RLS starves nothing and needs no code
change here.

Mechanism (see ``backend/app/db/session.py::_apply_tenant_rls``):
  - ``app.current_tenant`` — GUC pinned to the session tenant per transaction.
  - ``app.bypass_rls``      — ``'on'`` for trusted system/cross-tenant seeders/jobs.
Policy denies when neither is set (fail-closed). ``FORCE ROW LEVEL SECURITY`` makes
it apply even to the table owner. PostgreSQL-only.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20260724_sec65_rls_doc_pipeline"
down_revision: str | Sequence[str] | None = "20260724_sec65_rls_training_incidents_inspections"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Sorted; matches the live-metadata set for the file/package/pack_/pipeline/template/
# workflow prefixes. Legacy ``packagepreset``/``packageprofile`` have no underscore.
_TABLES = (
    "file",
    "file_content_index",
    "file_download_logs",
    "file_links",
    "file_objects",
    "file_scan_results",
    "file_text_index",
    "file_versions",
    "files",
    "pack_run_items",
    "pack_run_logs",
    "pack_runs",
    "package_events",
    "package_preset_items",
    "package_presets",
    "package_presets_v2",
    "package_profiles",
    "package_profiles_v2",
    "package_read_models",
    "package_requirements",
    "package_runs",
    "packagepreset",
    "packageprofile",
    "pipeline_profiles",
    "pipeline_runs",
    "pipeline_step_locks",
    "template",
    "templateusage",
    "templateversion",
    "workflow_definition_versions",
    "workflow_definitions",
    "workflow_instances",
    "workflow_tasks",
    "workflow_timeline_events",
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
