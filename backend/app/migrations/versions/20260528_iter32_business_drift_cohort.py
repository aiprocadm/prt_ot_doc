"""iter-32: retrofit nullable business columns surfaced by column_drift_lite audit.

Revision ID: 20260528_iter32_business_drift
Revises: 20260528_iter29_version_retrofit
Create Date: 2026-05-28

Bug class: ORM-Migration drift, flavor (b) — column declared on the model
but absent from the creator migration. Same family as iter-29 (which closed
the version-column mixin cohort), but for **business** columns rather than
mixin ones.

Discovered via ``scripts/audit/column_drift_lite.py`` (Session 80). The
audit reported 11 drift tables; this migration closes the safe-to-ship
subset where every column is either nullable or has a server-side default:

    permit:    position_id  (FK position.id ondelete SET NULL, nullable)
    ppeissue:  item_id      (FK ppeitem.id ondelete SET NULL, nullable)
               quantity     (Integer NOT NULL default 1)
               wear_days    (Integer nullable)
    riskmap:   document_pack_id  (FK document_pack.id, nullable)
               position_id       (FK position.id, nullable)
               site_id           (FK site.id, nullable)

Same operational impact as iter-29: every ORM UPDATE/INSERT that touches
these columns currently fails on Postgres with ``UndefinedColumnError``.
SQLite tolerant → e2e suite passes; perf-smoke / restore-drill / prod fail.

Deliberately deferred to a separate iter (needs design / backfill plan):
    ppenorm:   hazard_id    (NOT NULL FK — no safe server_default)
    riskmap:   company_id   (NOT NULL FK — no safe server_default)
    company:   inn, legal_address  (naming drift vs tax_id, address)
    npabinding: context, entity_id, entity_type
    journalentry: concept-level drift (payload/occurred_at vs metadata_json/entry_date)
    training_certificates: 4 cols marked "backward-compatible legacy" in model
    incident_log/incident_person/incident: design-blocked (Session 79)

FK semantics for ondelete are mirrored exactly from each model's
``mapped_column(ForeignKey(...))`` declaration so the migration matches
what SQLAlchemy expects to see.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260528_iter32_business_drift"
down_revision: str | Sequence[str] | None = "20260528_iter29_version_retrofit"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # permit.position_id ----------------------------------------------------
    op.add_column(
        "permit",
        sa.Column(
            "position_id",
            sa.String(length=36),
            sa.ForeignKey("position.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_permit_position_id", "permit", ["position_id"], unique=False)

    # ppeissue.{item_id, quantity, wear_days} -------------------------------
    op.add_column(
        "ppeissue",
        sa.Column(
            "item_id",
            sa.String(length=36),
            sa.ForeignKey("ppeitem.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "ppeissue",
        sa.Column(
            "quantity",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
    )
    op.add_column(
        "ppeissue",
        sa.Column("wear_days", sa.Integer(), nullable=True),
    )
    op.create_index("ix_ppeissue_item_id", "ppeissue", ["item_id"], unique=False)

    # riskmap.{document_pack_id, position_id, site_id} ----------------------
    op.add_column(
        "riskmap",
        sa.Column(
            "document_pack_id",
            sa.String(length=36),
            sa.ForeignKey("document_pack.id"),
            nullable=True,
        ),
    )
    op.add_column(
        "riskmap",
        sa.Column(
            "position_id",
            sa.String(length=36),
            sa.ForeignKey("position.id"),
            nullable=True,
        ),
    )
    op.add_column(
        "riskmap",
        sa.Column(
            "site_id",
            sa.String(length=36),
            sa.ForeignKey("site.id"),
            nullable=True,
        ),
    )
    op.create_index("ix_riskmap_document_pack_id", "riskmap", ["document_pack_id"], unique=False)
    op.create_index("ix_riskmap_position_id", "riskmap", ["position_id"], unique=False)
    op.create_index("ix_riskmap_site_id", "riskmap", ["site_id"], unique=False)


def downgrade() -> None:
    # Reverse order so downstream tooling observes inverse symmetry.
    op.drop_index("ix_riskmap_site_id", table_name="riskmap")
    op.drop_index("ix_riskmap_position_id", table_name="riskmap")
    op.drop_index("ix_riskmap_document_pack_id", table_name="riskmap")
    op.drop_column("riskmap", "site_id")
    op.drop_column("riskmap", "position_id")
    op.drop_column("riskmap", "document_pack_id")

    op.drop_index("ix_ppeissue_item_id", table_name="ppeissue")
    op.drop_column("ppeissue", "wear_days")
    op.drop_column("ppeissue", "quantity")
    op.drop_column("ppeissue", "item_id")

    op.drop_index("ix_permit_position_id", table_name="permit")
    op.drop_column("permit", "position_id")
