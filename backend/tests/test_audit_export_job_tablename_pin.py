"""Pin test for ``AuditExportJob.__tablename__`` rename to ``audit_export_job``.

iter-24 RB-002l (NEW release-blocker class — naming mismatch, not missing
table). Discovered by ``scripts/audit/check_orm_migration_drift.py`` (Session 71
flagged ``auditexportjob`` as ``critical`` while it was really a naming drift
between model and an already-existing migration).

Background:
  - Migration ``20260307_next37_audit_immutable_export.py:48`` creates table
    ``audit_export_job`` (snake_case) with all 14 columns the model needs.
  - Model class ``AuditExportJob`` inherits ``TenantBaseModel`` which defaults
    ``__tablename__ = cls.__name__.lower()`` = ``auditexportjob`` (no underscores).
  - Result: every ``session.get(AuditExportJob, ...)`` against Postgres raises
    ``UndefinedTableError: relation "auditexportjob" does not exist``.
    SQLite tests pass because ``Base.metadata.create_all()`` builds whatever
    the ORM says, so the discrepancy is invisible in CI until a real PG
    instance is hit (perf-smoke api-1 audit export endpoint).
  - Confirming evidence that snake_case is the *intended* canonical name:
      * Celery task module is ``app/celery/tasks/audit_export_job.py``.
      * Task is registered as ``app.tasks.audit_export_job``.
      * Model's own ``Index`` is named ``ix_audit_export_job_tenant_status``.

Fix: pin the explicit override ``__tablename__ = "audit_export_job"`` so a
future maintainer removing it (e.g. during a "cleanup" PR) immediately trips
this test before regression reaches Postgres.
"""

from __future__ import annotations

from app.models.models import AuditExportJob


def test_audit_export_job_tablename_uses_snake_case() -> None:
    assert AuditExportJob.__tablename__ == "audit_export_job", (
        "AuditExportJob.__tablename__ must be 'audit_export_job' (snake_case) "
        "to match the migration in 20260307_next37_audit_immutable_export.py. "
        "Default TenantBaseModel.__tablename__ derives 'auditexportjob' which "
        "would diverge from the deployed schema and crash ORM queries."
    )


def test_audit_export_job_table_object_name_matches() -> None:
    # Double-check via SQLAlchemy ``Table.name`` — paranoia against future
    # subclass tricks where __tablename__ is set on the class but the Mapped
    # __table__ is built from something else.
    assert AuditExportJob.__table__.name == "audit_export_job"
