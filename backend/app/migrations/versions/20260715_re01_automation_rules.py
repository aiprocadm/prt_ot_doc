"""re01: automation rules engine — rules + trigger log (P10-10 срез-1, vNext §25.2).

Additive. Adds:
- enum ruletriggerstatus + tables automation_rule / automation_rule_trigger
- enum label 'AutomationRule' on notificationtype (notify-действие движка)

Chains off cmt02. Downgrade drops tables/enum; enum LABEL на notificationtype
не удаляется (PG не умеет DROP VALUE) — безопасный no-op.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260715_re01_automation_rules"
down_revision = "20260714_cmt02_committee_proceedings"
branch_labels = None
depends_on = None

_TRIGGER_STATUS = postgresql.ENUM(
    "success", "partial", "error", name="ruletriggerstatus", create_type=False
)


def _common(*extra: sa.Column) -> list[sa.Column]:
    return [
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.String(length=36),
            sa.ForeignKey("tenant.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        *extra,
    ]


def _json_type(bind) -> sa.types.TypeEngine:
    return postgresql.JSONB() if bind.dialect.name == "postgresql" else sa.JSON()


def upgrade() -> None:
    bind = op.get_bind()
    json_t = _json_type(bind)
    if bind.dialect.name == "postgresql":
        _TRIGGER_STATUS.create(bind, checkfirst=True)
        # Новый label для notify-действия движка. IF NOT EXISTS — идемпотентно (PG>=12).
        # POST-2: enum extension commits outside the migration tx (PG forbids
        # using a new value in the tx that added it).
        with op.get_context().autocommit_block():
            op.execute("ALTER TYPE notificationtype ADD VALUE IF NOT EXISTS 'AutomationRule'")

    op.create_table(
        "automation_rule",
        *_common(
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("event_type", sa.String(length=64), nullable=False),
            sa.Column("conditions_json", json_t, nullable=False),
            sa.Column("actions_json", json_t, nullable=False),
            sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
            sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        ),
        sa.UniqueConstraint("tenant_id", "name", name="uq_automation_rule_tenant_name"),
    )
    op.create_index(
        "ix_automation_rule_tenant_event", "automation_rule", ["tenant_id", "event_type"]
    )

    trigger_status_col = (
        _TRIGGER_STATUS
        if bind.dialect.name == "postgresql"
        else sa.Enum("success", "partial", "error", name="ruletriggerstatus", native_enum=False)
    )
    op.create_table(
        "automation_rule_trigger",
        *_common(
            sa.Column(
                "rule_id",
                sa.String(length=36),
                sa.ForeignKey("automation_rule.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column("event_type", sa.String(length=64), nullable=False),
            sa.Column("event_key", sa.String(length=255), nullable=False),
            sa.Column("correlation_id", sa.String(length=128), nullable=True),
            sa.Column("event_payload", json_t, nullable=False),
            sa.Column("status", trigger_status_col, nullable=False),
            sa.Column("actions_result", json_t, nullable=False),
        ),
    )
    op.create_index(
        "ix_automation_rule_trigger_rule_created",
        "automation_rule_trigger",
        ["tenant_id", "rule_id", "created_at"],
    )
    op.create_index(
        "ix_automation_rule_trigger_tenant_created",
        "automation_rule_trigger",
        ["tenant_id", "created_at"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    op.drop_index("ix_automation_rule_trigger_tenant_created", table_name="automation_rule_trigger")
    op.drop_index("ix_automation_rule_trigger_rule_created", table_name="automation_rule_trigger")
    op.drop_table("automation_rule_trigger")
    op.drop_index("ix_automation_rule_tenant_event", table_name="automation_rule")
    op.drop_table("automation_rule")
    if bind.dialect.name == "postgresql":
        _TRIGGER_STATUS.drop(bind, checkfirst=True)
        # label 'AutomationRule' на notificationtype остаётся — PG не умеет удалять значения enum.
