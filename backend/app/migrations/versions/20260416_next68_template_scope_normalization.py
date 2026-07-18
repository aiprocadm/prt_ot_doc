"""NEXT-68: normalize template scope/category columns.

Revision ID: 20260416_next68_template_scope_normalization
Revises: 20260318_next67_risk_custom_enum_hotfix
Create Date: 2026-04-16
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.engine import Connection

# revision identifiers, used by Alembic.
revision: str = "20260416_next68_template_scope_normalization"
down_revision: str | Sequence[str] | None = "20260318_next67_risk_custom_enum_hotfix"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _normalize_scope_level(raw_scope: dict[str, Any] | None) -> str:
    scope = raw_scope or {}
    level = str(scope.get("type") or scope.get("level") or "tenant").strip().lower()
    aliases = {
        "branch": "site",
        "organization": "company",
        "legal_entity": "company",
        "global": "system",
    }
    normalized = aliases.get(level, level)
    if normalized not in {"tenant", "company", "site", "system"}:
        return "tenant"
    return normalized


def _backfill_template_scope(conn: Connection) -> None:
    rows = conn.execute(
        sa.text(
            """
            SELECT id, metadata_json
            FROM template
            """
        )
    ).mappings()

    for row in rows:
        metadata = row.get("metadata_json") if isinstance(row.get("metadata_json"), dict) else {}
        scope = metadata.get("scope") if isinstance(metadata.get("scope"), dict) else {}
        category = metadata.get("category")
        level = _normalize_scope_level(scope)
        company_id = scope.get("company_id")
        site_id = scope.get("site_id")
        tags = metadata.get("tags") if isinstance(metadata.get("tags"), list) else None
        conn.execute(
            sa.text(
                """
                UPDATE template
                SET category = :category,
                    scope_level = :scope_level,
                    scope_company_id = :scope_company_id,
                    scope_site_id = :scope_site_id,
                    tags_json = :tags_json
                WHERE id = :template_id
                """
            ),
            {
                "template_id": row["id"],
                "category": category if isinstance(category, str) else None,
                "scope_level": level,
                "scope_company_id": str(company_id) if company_id else None,
                "scope_site_id": str(site_id) if site_id else None,
                "tags_json": tags,
            },
        )


def upgrade() -> None:
    op.add_column("template", sa.Column("category", sa.String(length=255), nullable=True))
    op.add_column(
        "template",
        sa.Column("scope_level", sa.String(length=32), nullable=False, server_default="tenant"),
    )
    op.add_column("template", sa.Column("scope_company_id", sa.String(length=36), nullable=True))
    op.add_column("template", sa.Column("scope_site_id", sa.String(length=36), nullable=True))
    op.add_column("template", sa.Column("tags_json", sa.JSON(), nullable=True))

    op.create_index(op.f("ix_template_category"), "template", ["category"], unique=False)
    op.create_index(op.f("ix_template_scope_level"), "template", ["scope_level"], unique=False)
    op.create_index(
        "ix_template_scope_level_company_site",
        "template",
        ["tenant_id", "scope_level", "scope_company_id", "scope_site_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_template_scope_company_id"),
        "template",
        ["scope_company_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_template_scope_site_id"),
        "template",
        ["scope_site_id"],
        unique=False,
    )

    conn = op.get_bind()
    _backfill_template_scope(conn)

    op.alter_column("template", "scope_level", server_default=None)


def downgrade() -> None:
    op.drop_index(op.f("ix_template_scope_site_id"), table_name="template")
    op.drop_index(op.f("ix_template_scope_company_id"), table_name="template")
    op.drop_index("ix_template_scope_level_company_site", table_name="template")
    op.drop_index(op.f("ix_template_scope_level"), table_name="template")
    op.drop_index(op.f("ix_template_category"), table_name="template")

    op.drop_column("template", "tags_json")
    op.drop_column("template", "scope_site_id")
    op.drop_column("template", "scope_company_id")
    op.drop_column("template", "scope_level")
    op.drop_column("template", "category")
