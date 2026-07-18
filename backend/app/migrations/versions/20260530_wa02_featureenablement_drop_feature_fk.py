"""drop cross-base featureenablement -> feature FK (W-A / TZ-3.2-V11-01)

Corrective parity migration. The initial schema (``6b6dee7c951f``) created
``featureenablement`` with an (unnamed) ForeignKey to the shared ``feature``
table::

    sa.ForeignKeyConstraint(['feature_id'], ['feature.id'], ondelete='CASCADE')

``FeatureEnablement`` is a TenantBaseModel (TenantBase metadata) while
``Feature`` is a SharedModel (SharedBase metadata); a SQLAlchemy ForeignKey
across the two declarative metadatas is unresolvable during the
create_all-first boot used by the test harness and raises
``NoReferencedTableError``. The ORM model was changed to keep ``feature_id`` a
plain ``String(36)`` column (cross-base FKs are unenforceable in this
two-metadata setup anyway). This migration brings the database into parity by
dropping the now-orphaned FK constraint.

Everything else on ``featureenablement`` / ``feature`` is left intact (columns,
indexes, the ``uq_feature_enablement_tenant_feature`` unique constraint). No
data backfill. Postgres-only: the SQLite dev/test path builds its schema from
ORM metadata via ``create_all``, which no longer declares the FK, so there is
nothing to drop there.

Chains off the W-A head (``20260529_wa01_ppe_stock_batch``). The repo runs
``alembic upgrade heads`` (plural — many heads by design), so this additive
change applies regardless of the other parallel branches.

Revision ID: 20260530_wa02_featureenablement_drop_feature_fk
Revises: 20260529_wa01_ppe_stock_batch
Create Date: 2026-05-30 00:00:00.000000
"""

from __future__ import annotations

from alembic import op

revision = "20260530_wa02_featureenablement_drop_feature_fk"
down_revision = "20260529_wa01_ppe_stock_batch"
branch_labels = None
depends_on = None

# Postgres default name for the unnamed ``featureenablement(feature_id)`` ->
# ``feature(id)`` FK created by the initial migration (no naming_convention is
# configured on the metadata, so the ``<table>_<column>_fkey`` default applies).
_FK_NAME = "featureenablement_feature_id_fkey"


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # IF EXISTS keeps this idempotent and safe across environments where the
        # constraint may already be absent (e.g. a DB bootstrapped via create_all
        # rather than this migration chain).
        op.execute(f'ALTER TABLE featureenablement DROP CONSTRAINT IF EXISTS "{_FK_NAME}"')


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.create_foreign_key(
            _FK_NAME,
            "featureenablement",
            "feature",
            ["feature_id"],
            ["id"],
            ondelete="CASCADE",
        )
