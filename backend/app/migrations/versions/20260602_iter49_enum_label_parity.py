"""iter-49: ORM<->pg_enum label parity — backfill missing .value labels.

The ORM now binds enum member .value (via native_enum/values_callable) for 52
columns whose pg_enum types were created with .value labels. Four of those types
are missing some .value labels; add them so ORM inserts succeed:

  documentstatus       += archived, draft, review, signed  (had only UPPER variants)
  notificationchannel  += webhook
  notificationtype     += 11 newer members (notifications.type; the *template* type
                          notificationtemplatetype is already complete)
  roleenum             += 9 lowercase roles (had UPPER variants / were absent)

ADD VALUE IF NOT EXISTS is idempotent and retry-safe under the env.py AUTOCOMMIT +
transaction_per_migration config (the labels are NOT used as a server_default in
this migration, so no UnsafeNewEnumValueUsageError). SQLite is a no-op (Enum->VARCHAR).

Heads-merge: at authoring time the tree had 8 divergent heads (iter43 docstring
noted the pending merge). This revision's down_revision is the tuple of all 8, so
it doubles as the merge -> single head.

Downgrade: no-op. PG has no DROP VALUE; the added labels are additive and harmless.

Pre-existing data caveat (out of scope, documented in KNOWN_LIMITATIONS.md): rows
written before this change under the old name-binding behavior may hold UPPER
strings (role, document.status) and would need a one-time UPDATE backfill. Fresh-PG
(the canonical target) is unaffected.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20260602_iter49_enum_label_parity"
down_revision: str | Sequence[str] | None = (
    "20260529_iter35_riskmap_company",
    "20260529_iter40_tc_legacy_cols",
    "20260529_iter41_journalentry_concept",
    "20260529_iter42_incident_family",
    "20260529_iter43_incident_status_enum",
    "20260529_iter46_approval_decisions_cols",
    "20260529_iter47_file_business_cols",
    "20260530_wa03_prescription_lifecycle",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# pg type -> missing labels (authoritative: 2026-06-02 fresh-PG audit).
ADD_VALUES: dict[str, tuple[str, ...]] = {
    "documentstatus": ("archived", "draft", "review", "signed"),
    "notificationchannel": ("webhook",),
    "notificationtype": (
        "ApprovalDeadline",
        "BillingLimitWarning",
        "EdoStatusChanged",
        "IncidentCreated",
        "InspectionCreated",
        "IntegrationError",
        "MedicalOverdue",
        "PPEOverdue",
        "PackageRunCompleted",
        "PackageRunFailed",
        "PrescriptionOverdue",
    ),
    "roleenum": (
        "auditor_ro",
        "clerk",
        "client",
        "executor",
        "inspector_contractor",
        "manager",
        "ot_head",
        "student",
        "teacher",
    ),
}


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    # POST-2: enum extension commits outside the migration tx (PG forbids
    # using a new value in the tx that added it); IF NOT EXISTS = retry-safe.
    with op.get_context().autocommit_block():
        for type_name, values in ADD_VALUES.items():
            for value in values:
                op.execute(f"ALTER TYPE {type_name} ADD VALUE IF NOT EXISTS '{value}'")


def downgrade() -> None:
    # No-op: PG has no DROP VALUE; added labels are additive and harmless.
    pass
