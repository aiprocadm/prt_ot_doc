"""iter-42: incident family cohort closure — last 3 column_drift_lite tables.

Closes the FINAL 3 business-drift tables surfaced by ``column_drift_lite``
(Session 85 baseline, after iters 39/40/41 close npabinding,
training_certificates, journalentry):

  - ``incident`` (alter): add 6 missing cols + 4 model-aligned indexes.
  - ``incident_log`` (create_table): entirely absent from migrations.
  - ``incident_person`` (create_table): entirely absent from migrations.

Plus 5 new PG enum types:
  - ``incidenttype`` (accident/microtrauma/near_miss/unsafe_condition).
  - ``incidentstage`` (registration/investigation/action_plan/follow_up/closed).
  - ``incidentpersonrole`` (victim/witness/participant).
  - ``incidentlogstage`` (same shape as incidentstage but separate PG name).
  - ``incidentlogstatus`` (reported/investigating/corrective_actions/closed/cancelled).

Pre-existing enums reused as-is:
  - ``incidentseverity`` (LOW/MEDIUM/HIGH) — created by initial_schema.

OUT OF SCOPE for iter-42:
  - ``incident.status`` column type drift (migration has ``String(64)``,
    model has ``Enum(IncidentStatus, name="incidentstatus")``). This is
    type drift, not column-presence drift; column_drift_lite doesn't flag it.
    A future iter can alter the type with a CAST and create the
    ``incidentstatus`` PG enum, but it requires understanding whether any
    existing rows hold values that need normalization.

Data-loss assumption (per user choice — Option A in S88→89 design Q):
  The ``incident`` table is assumed empty in any deployed environment.
  Two of the 6 new cols (``company_id``, ``site_id``) are NOT NULL FKs
  with no safe server_default and no backfill source. The migration will
  FAIL with ``NotNullViolation`` if non-empty.

  This assumption is operationally justified: the API surface in
  ``backend/app/api/routes/incidents.py`` writes via ORM with all model
  cols set; the missing migration cols mean such writes have always
  raised ``UndefinedColumnError`` on PostgreSQL → no real data sits in
  the table. Mirror of the iter-41 reasoning for ``journalentry``.

  Pre-deploy verification: ``SELECT count(*) FROM incident`` against
  prod. If non-zero, decide between dump-and-recreate (mirror iter-41)
  or backfill plan before applying.

Mixin awareness:
  - ``incident`` inherits ``TenantBaseModel + SoftDeleteMixin`` — has
    deleted_at + standard mixins (already in original create_table).
  - ``incident_log`` inherits ``TenantBaseModel`` only — no deleted_at.
  - ``incident_person`` inherits ``TenantBaseModel`` only — no deleted_at.

After iter-42 lands, column_drift_lite business-drift drops from
3 → 0 (assuming iters 39/40/41 also landed). The drift class
column_drift_lite is fully closed for business cols at this point.

NOTE on alembic heads: this migration chains from
``20260529_iter38_server_default_c`` (latest revision on ``main`` at
session-start). The parallel branches ``iter-40`` and ``iter-41`` ALSO
chain from the same parent. When 3+ migration-bearing branches all
land on main, alembic merge-heads will be required to unify them.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260529_iter42_incident_family"
down_revision: str | Sequence[str] | None = "20260529_iter38_server_default_c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Enum members are the UPPER_CASE Python attribute names (SA's default
# storage form for Enum(EnumClass, name=X) without values_callable).
# Mirror model definitions in backend/app/models/models.py:2260-2280, 2335-2339.

INCIDENT_TYPE_VALUES = ("ACCIDENT", "MICROTRAUMA", "NEAR_MISS", "UNSAFE_CONDITION")
INCIDENT_STAGE_VALUES = (
    "REGISTRATION", "INVESTIGATION", "ACTION_PLAN", "FOLLOW_UP", "CLOSED",
)
INCIDENT_PERSON_ROLE_VALUES = ("VICTIM", "WITNESS", "PARTICIPANT")
# IncidentLog reuses IncidentStage Python class but declares a separate PG
# enum name (per model:2378). Same values, distinct PG type. Spelled out
# in full rather than aliased so the migration is self-explanatory and
# AST analyzers (pin tests) can read the values directly.
INCIDENT_LOG_STAGE_VALUES = (
    "REGISTRATION", "INVESTIGATION", "ACTION_PLAN", "FOLLOW_UP", "CLOSED",
)
# IncidentLog.status uses IncidentStatus Python class with a separate PG
# enum name. Values match model:2267-2272.
INCIDENT_LOG_STATUS_VALUES = (
    "REPORTED", "INVESTIGATING", "ACTIONS", "CLOSED", "CANCELLED",
)


def upgrade() -> None:
    # Explicitly create the PG enum types up front (checkfirst=True). Under
    # AUTOCOMMIT + transaction_per_migration the implicit CREATE TYPE that
    # add_column would emit is unreliable, so create them here (mirrors
    # iter47 / next55). No-op on SQLite.
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        postgresql.ENUM(*INCIDENT_TYPE_VALUES, name="incidenttype", create_type=False).create(bind, checkfirst=True)
        postgresql.ENUM(*INCIDENT_STAGE_VALUES, name="incidentstage", create_type=False).create(bind, checkfirst=True)
    # ------------------------------------------------------------------
    # 1. Alter incident: add 6 missing business cols + 4 indexes.
    # ------------------------------------------------------------------
    op.add_column(
        "incident",
        sa.Column(
            "company_id",
            sa.String(length=36),
            sa.ForeignKey("company.id"),
            nullable=False,
        ),
    )
    op.add_column(
        "incident",
        sa.Column(
            "site_id",
            sa.String(length=36),
            sa.ForeignKey("site.id"),
            nullable=False,
        ),
    )
    op.add_column(
        "incident",
        sa.Column(
            "incident_type",
            postgresql.ENUM(*INCIDENT_TYPE_VALUES, name="incidenttype", create_type=False),
            nullable=False,
            server_default="ACCIDENT",
        ),
    )
    op.add_column(
        "incident",
        sa.Column(
            "investigation_stage",
            postgresql.ENUM(*INCIDENT_STAGE_VALUES, name="incidentstage", create_type=False),
            nullable=False,
            server_default="REGISTRATION",
        ),
    )
    op.add_column(
        "incident",
        sa.Column("location_description", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "incident",
        sa.Column(
            "pack_id",
            sa.String(length=36),
            sa.ForeignKey("document_pack.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    # Column-level indexes (from model `index=True` flags).
    op.create_index("ix_incident_company_id", "incident", ["company_id"], unique=False)
    op.create_index("ix_incident_site_id", "incident", ["site_id"], unique=False)
    op.create_index("ix_incident_pack_id", "incident", ["pack_id"], unique=False)
    # Composite indexes (from model __table_args__).
    op.create_index("ix_incident_company", "incident", ["tenant_id", "company_id"], unique=False)
    op.create_index("ix_incident_site", "incident", ["tenant_id", "site_id"], unique=False)
    op.create_index("ix_incident_status", "incident", ["tenant_id", "status"], unique=False)
    op.create_index("ix_incident_occurred_at", "incident", ["occurred_at"], unique=False)

    # ------------------------------------------------------------------
    # 2. Create incident_log table.
    # ------------------------------------------------------------------
    op.create_table(
        "incident_log",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("incident_id", sa.String(length=36), nullable=False),
        sa.Column("author_id", sa.String(length=36), nullable=True),
        sa.Column(
            "stage",
            postgresql.ENUM(*INCIDENT_LOG_STAGE_VALUES, name="incidentlogstage", create_type=False),
            nullable=False,
        ),
        sa.Column(
            "status",
            postgresql.ENUM(*INCIDENT_LOG_STATUS_VALUES, name="incidentlogstatus", create_type=False),
            nullable=False,
        ),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.ForeignKeyConstraint(["incident_id"], ["incident.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["author_id"], ["user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_incident_log_tenant_id"), "incident_log", ["tenant_id"], unique=False)
    op.create_index("ix_incident_log_incident_id", "incident_log", ["incident_id"], unique=False)
    op.create_index("ix_incident_log_author_id", "incident_log", ["author_id"], unique=False)
    op.create_index("ix_incident_log_incident", "incident_log", ["tenant_id", "incident_id"], unique=False)
    op.create_index("ix_incident_log_stage", "incident_log", ["tenant_id", "stage"], unique=False)

    # ------------------------------------------------------------------
    # 3. Create incident_person table.
    # ------------------------------------------------------------------
    op.create_table(
        "incident_person",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("incident_id", sa.String(length=36), nullable=False),
        sa.Column("person_id", sa.String(length=36), nullable=False),
        sa.Column(
            "role",
            postgresql.ENUM(*INCIDENT_PERSON_ROLE_VALUES, name="incidentpersonrole", create_type=False),
            nullable=False,
            server_default="VICTIM",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.ForeignKeyConstraint(["incident_id"], ["incident.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["person_id"], ["person.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "incident_id",
            "person_id",
            "role",
            name="uq_incident_person_role",
        ),
    )
    op.create_index(op.f("ix_incident_person_tenant_id"), "incident_person", ["tenant_id"], unique=False)
    op.create_index("ix_incident_person_incident_id", "incident_person", ["incident_id"], unique=False)
    op.create_index("ix_incident_person_person_id", "incident_person", ["person_id"], unique=False)
    op.create_index("ix_incident_person_role", "incident_person", ["role"], unique=False)


def downgrade() -> None:
    # ------------------------------------------------------------------
    # 3. Drop incident_person.
    # ------------------------------------------------------------------
    op.drop_index("ix_incident_person_role", table_name="incident_person")
    op.drop_index("ix_incident_person_person_id", table_name="incident_person")
    op.drop_index("ix_incident_person_incident_id", table_name="incident_person")
    op.drop_index(op.f("ix_incident_person_tenant_id"), table_name="incident_person")
    op.drop_table("incident_person")
    sa.Enum(name="incidentpersonrole").drop(op.get_bind(), checkfirst=True)

    # ------------------------------------------------------------------
    # 2. Drop incident_log.
    # ------------------------------------------------------------------
    op.drop_index("ix_incident_log_stage", table_name="incident_log")
    op.drop_index("ix_incident_log_incident", table_name="incident_log")
    op.drop_index("ix_incident_log_author_id", table_name="incident_log")
    op.drop_index("ix_incident_log_incident_id", table_name="incident_log")
    op.drop_index(op.f("ix_incident_log_tenant_id"), table_name="incident_log")
    op.drop_table("incident_log")
    sa.Enum(name="incidentlogstatus").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="incidentlogstage").drop(op.get_bind(), checkfirst=True)

    # ------------------------------------------------------------------
    # 1. Revert incident alterations.
    # ------------------------------------------------------------------
    op.drop_index("ix_incident_occurred_at", table_name="incident")
    op.drop_index("ix_incident_status", table_name="incident")
    op.drop_index("ix_incident_site", table_name="incident")
    op.drop_index("ix_incident_company", table_name="incident")
    op.drop_index("ix_incident_pack_id", table_name="incident")
    op.drop_index("ix_incident_site_id", table_name="incident")
    op.drop_index("ix_incident_company_id", table_name="incident")
    op.drop_column("incident", "pack_id")
    op.drop_column("incident", "location_description")
    op.drop_column("incident", "investigation_stage")
    op.drop_column("incident", "incident_type")
    op.drop_column("incident", "site_id")
    op.drop_column("incident", "company_id")
    sa.Enum(name="incidentstage").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="incidenttype").drop(op.get_bind(), checkfirst=True)
