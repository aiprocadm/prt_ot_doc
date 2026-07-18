"""Backfill pack item template versions.

Revision ID: 20250318_pack_item_template_version
Revises: 20250315_platform_p0_document_snapshot_batch
Create Date: 2025-03-18 00:00:00.000000
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20250318_pack_item_template_version"
down_revision: str | tuple[str, ...] = "20250315_platform_p0_document_snapshot_batch"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    # NOTE: SQLAlchemy's default ``Enum(SomeEnum)`` stores the enum **member name**
    # in PostgreSQL (e.g. ``'ACTIVE'``), not the Python value (``'active'``). Earlier
    # versions of this migration used the lowercase value, which crashed on PG with
    # ``invalid input value for enum templateversionstatus: "active"``. SQLite was
    # silently accepting it because its Enum is just a TEXT-like column without
    # strict label checking. The codebase already standardises on ``.name`` for
    # raw SQL lookups (see ``backend/app/cli/main.py`` and ORM filters comparing to
    # ``TemplateVersionStatus.ACTIVE`` enum literal). Fix here brings the migration
    # in line with that convention.
    op.execute(
        """
        WITH latest AS (
            SELECT DISTINCT ON (template_id) id, template_id
            FROM templateversion
            WHERE status = 'ACTIVE'
            ORDER BY template_id, version DESC
        )
        UPDATE document_pack_item AS dpi
        SET template_version_id = latest.id
        FROM latest
        WHERE dpi.template_version_id IS NULL
          AND dpi.template_id = latest.template_id
        """
    )


def downgrade() -> None:
    op.execute("UPDATE document_pack_item SET template_version_id = NULL")
