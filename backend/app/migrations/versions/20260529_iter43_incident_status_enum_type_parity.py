"""iter-43: incident.status type-parity — String(64) → Enum(incidentstatus).

Closes the type drift surfaced as out-of-scope by iter-42 (Session 89).
The ``incident.status`` column is declared as
``Mapped[IncidentStatus] = mapped_column(Enum(IncidentStatus, name="incidentstatus"))``
in the model (``backend/app/models/models.py:2300``) but exists as
``String(64)`` in the migration (``6b6dee7c951f_initial_schema.py:199``).

Functionally tolerated by SQLAlchemy (SA stores the attribute-name string
for Enum cols by default; String(64) accepts those same strings), but
inconsistent with the other 4 enum cols on the same table (severity,
incident_type, investigation_stage, status — all but status are Enums).

This iter creates the missing ``incidentstatus`` PG enum type and alters
the column to use it. Same UPPER_CASE attribute-name values as iter-38
established for SA Enum(EnumClass) storage form.

Mirrors iter-37's audit-extension precedent for ``alter_column`` work,
and iter-38's UPPER_CASE label convention.

Empty-table assumption (inherited from iter-42 reasoning):
  The ``USING status::text::incidentstatus`` cast on PG would fail if any
  existing row has a string value not in the enum's UPPER_CASE label set
  (e.g. ``'pending'`` or ``'unknown'``). The reasoning in iter-42 covers
  this case: ``incident`` table is assumed empty in any deployed
  environment because the API surface in ``incidents.py`` has been broken
  on the column-presence drift since the model evolved.

  Pre-deploy verification: ``SELECT DISTINCT status FROM incident`` against
  prod. If any value is outside ``{REPORTED, INVESTIGATING, ACTIONS,
  CLOSED, CANCELLED}``, normalize before applying iter-43.

SQLite portability:
  ``op.batch_alter_table`` is used because SQLite doesn't support ALTER
  COLUMN TYPE — Alembic emulates via table-rebuild. The
  ``postgresql_using`` kwarg is a dialect-specific hint, ignored on
  SQLite. On SQLite the Enum becomes VARCHAR with optional CHECK
  constraint.

NOTE on alembic heads: this chains from ``20260529_iter38_server_default_c``
(same parent as iter-40, iter-41, iter-42). iter-43 touches only
``incident.status`` (an EXISTING col), while iter-42 adds 6 NEW cols to
the same table — no column-level conflict. After merge, alembic needs
``alembic merge heads`` to unify the divergent heads.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260529_iter43_incident_status_enum"
down_revision: str | Sequence[str] | None = "20260529_iter38_server_default_c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Mirror of model:2267-2272 (IncidentStatus enum class). UPPER_CASE
# attribute names are the SA default storage form for Enum(EnumClass).
INCIDENT_STATUS_VALUES = (
    "REPORTED",
    "INVESTIGATING",
    "ACTIONS",
    "CLOSED",
    "CANCELLED",
)


def upgrade() -> None:
    bind = op.get_bind()
    incident_status_enum = sa.Enum(*INCIDENT_STATUS_VALUES, name="incidentstatus")
    incident_status_enum.create(bind, checkfirst=True)
    # PG cannot ALTER COLUMN TYPE while a server_default exists that it can't
    # auto-cast to the new enum type (iter-37/38 left a plain-string default
    # like 'REPORTED'). Drop the default, change the type, then re-establish
    # the default as the enum value. batch_alter_table handles SQLite (which
    # has no ALTER TYPE and no such default-cast constraint).
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TABLE incident ALTER COLUMN status DROP DEFAULT")
    with op.batch_alter_table("incident", schema=None) as batch_op:
        batch_op.alter_column(
            "status",
            existing_type=sa.String(length=64),
            type_=incident_status_enum,
            existing_nullable=False,
            postgresql_using="status::text::incidentstatus",
        )
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TABLE incident ALTER COLUMN status SET DEFAULT 'REPORTED'")


def downgrade() -> None:
    with op.batch_alter_table("incident", schema=None) as batch_op:
        batch_op.alter_column(
            "status",
            existing_type=sa.Enum(*INCIDENT_STATUS_VALUES, name="incidentstatus"),
            type_=sa.String(length=64),
            existing_nullable=False,
        )
    sa.Enum(name="incidentstatus").drop(op.get_bind(), checkfirst=True)
