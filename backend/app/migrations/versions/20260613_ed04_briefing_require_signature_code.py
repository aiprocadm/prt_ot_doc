"""ed04: BriefingTemplate.require_signature_code (TZ B.5, vNext §6.9 Срез-3).

Additive. One non-null boolean column (server_default false) on briefing_templates
to opt a briefing type into code-flow signing. Round-trip-safe: downgrade drops it.
Table/column names are LITERAL (AST-audit blindspot).
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260613_ed04_briefing_require_signature_code"
down_revision = "20260613_med02_medical_factor_catalog"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "briefing_templates",
        sa.Column(
            "require_signature_code",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("briefing_templates", "require_signature_code")
