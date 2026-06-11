"""sz02: DROP dead family-B PPE tables (orphaned by СИЗ Срез-1 ORM cleanup).

The family-B PPE contour (next58, 2026-04-01) never grew a write path; its
ORM classes were deleted from the codebase in СИЗ Срез-1:

  * PPECatalog / PPENormDoc / PPENormItem / PPEIssueRecord / PPEPersonalCard /
    PPEPersonalCardItem — removed from app/models/safety_core.py (PR #647);
  * WarehousePPE — removed from app/models/models.py (orphan, table from the
    initial schema 6b6dee7c951f).

The live PPE contour (family A: ppenorm / ppeitem / ppeissue / ppe_stock_batch,
app/models/models.py) is named WITHOUT underscores and is NOT touched here.

Upgrade drops the seven dead tables, children before parents (their indexes
drop together with the tables on both PG and SQLite). No enum types are
involved — every column is a primitive type.

Downgrade recreates the tables exactly as their creating migrations defined
them, in the state they would have at this chain position:

  * the six ppe_* tables + 3 composite indexes — verbatim from next58;
  * warehouseppe + ix_warehouseppe_tenant_id — verbatim from the initial
    schema, plus ``quantity`` ``server_default="0"`` because iter37
    (20260529_iter37_server_default_ab) had already applied it by this point;
    iter37's own downgrade then resets it on the way to base (round-trip
    symmetry: ``upgrade heads`` -> ``downgrade base`` -> ``upgrade heads``).
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260611_sz02_drop_ppe_family_b_tables"
down_revision = "20260610_sz01_ppe_norms_card_766n"
branch_labels = None
depends_on = None

# FK-dependency-safe DROP order: children (link tables) before parents.
DROPPED_TABLES = (
    "ppe_personal_card_items",  # FK -> ppe_personal_cards, ppe_catalog, ppe_issues
    "ppe_personal_cards",       # FK -> persons
    "ppe_issues",               # FK -> persons, ppe_catalog, ppe_norm_items
    "ppe_norm_items",           # FK -> ppe_norms, ppe_catalog
    "ppe_norms",
    "ppe_catalog",
    "warehouseppe",             # FK -> tenant only; independent of the six above
)


def _audit_cols() -> list[sa.Column]:
    # Same helper shape as next58 — the family-B tables carried these.
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    ]


def upgrade() -> None:
    for table in DROPPED_TABLES:
        op.drop_table(table)


def downgrade() -> None:
    # --- family-B PPE tables, verbatim from next58 (parents first) -------
    op.create_table(
        "ppe_catalog",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("code", sa.String(64), nullable=True),
        sa.Column("sku", sa.String(64), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("category", sa.String(64), nullable=True),
        sa.Column("size_grid_json", sa.JSON(), nullable=True),
        sa.Column("wear_term_months", sa.Integer(), nullable=True),
        sa.Column("certificate_no", sa.String(128), nullable=True),
        sa.Column("certificate_expiry", sa.Date(), nullable=True),
        sa.Column("unit", sa.String(16), nullable=False, server_default="pcs"),
        *_audit_cols(),
    )
    op.create_table(
        "ppe_norms",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("code", sa.String(64), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=True),
        sa.Column("effective_to", sa.Date(), nullable=True),
        *_audit_cols(),
    )
    op.create_table(
        "ppe_norm_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("ppe_norm_id", sa.String(36), sa.ForeignKey("ppe_norms.id"), nullable=False),
        sa.Column("applies_to_type", sa.String(32), nullable=False),
        sa.Column("applies_to_id", sa.String(36), nullable=False),
        sa.Column("ppe_catalog_id", sa.String(36), sa.ForeignKey("ppe_catalog.id"), nullable=False),
        sa.Column("quantity", sa.Numeric(10, 2), nullable=False),
        sa.Column("period_months", sa.Integer(), nullable=True),
        sa.Column("size_required", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "ppe_issues",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("person_id", sa.String(36), sa.ForeignKey("persons.id"), nullable=False),
        sa.Column("ppe_catalog_id", sa.String(36), sa.ForeignKey("ppe_catalog.id"), nullable=False),
        sa.Column("issue_type", sa.String(32), nullable=False),
        sa.Column("quantity", sa.Numeric(10, 2), nullable=False),
        sa.Column("size", sa.String(32), nullable=True),
        sa.Column("serial_no", sa.String(128), nullable=True),
        sa.Column("batch_no", sa.String(128), nullable=True),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("due_return_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("basis_text", sa.Text(), nullable=True),
        sa.Column("related_norm_item_id", sa.String(36), sa.ForeignKey("ppe_norm_items.id"), nullable=True),
        sa.Column("issued_by", sa.String(36), nullable=True),
        *_audit_cols(),
    )
    op.create_table(
        "ppe_personal_cards",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("person_id", sa.String(36), sa.ForeignKey("persons.id"), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        *_audit_cols(),
        sa.UniqueConstraint("person_id", name="uq_ppe_personal_cards_person"),
    )
    op.create_table(
        "ppe_personal_card_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("personal_card_id", sa.String(36), sa.ForeignKey("ppe_personal_cards.id"), nullable=False),
        sa.Column("ppe_catalog_id", sa.String(36), sa.ForeignKey("ppe_catalog.id"), nullable=False),
        sa.Column("last_issue_id", sa.String(36), sa.ForeignKey("ppe_issues.id"), nullable=True),
        sa.Column("current_quantity", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("next_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    # next58 created these explicitly; its downgrade drops them explicitly —
    # they must exist again for `downgrade base` to pass through next58.
    op.create_index("ix_ppe_norm_items_filter", "ppe_norm_items", ["ppe_norm_id", "applies_to_type", "applies_to_id"])
    op.create_index("ix_ppe_issues_filter", "ppe_issues", ["tenant_id", "person_id", "ppe_catalog_id", "issued_at"])
    op.create_index("ix_ppe_personal_card_items_filter", "ppe_personal_card_items", ["personal_card_id", "ppe_catalog_id"])

    # --- warehouseppe, verbatim from the initial schema 6b6dee7c951f ------
    # plus quantity server_default="0" (iter37 state at this chain position).
    op.create_table(
        "warehouseppe",
        sa.Column("item_name", sa.String(length=255), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("id", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_warehouseppe_tenant_id"), "warehouseppe", ["tenant_id"], unique=False)
