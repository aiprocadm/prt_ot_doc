"""iter-47: file model-col closure.

Closes the ``file`` business-drift table surfaced by ``column_drift_lite``
(Session 95 candidate #1). The legacy ``File`` model
(``backend/app/models/file.py``) grew **eight** columns over the
clamav/quarantine + pack/company build-out that no migration ever creates:

    original_name      String(255)                       nullable
    kind               Enum(file_kind)        NOT NULL    server_default DOCUMENT
    company_id         String(36)                         nullable, indexed
    pack_id            String(36)                         nullable, indexed
    is_quarantined     Boolean                NOT NULL    server_default true
    scan_status        Enum(file_scan_status) NOT NULL    server_default PENDING
    clamav_signature   String(255)                        nullable
    clamav_scanned_at  DateTime(timezone=True)            nullable

The only migrations that touch ``file`` predate these cols:
``6b6dee7c951f_initial_schema`` (storage_key, sha256, size, mime, meta_json +
base) and ``8d2c1a6c5e24_domain_normalization`` (bucket). The eight cols are
live read/written in production — ``app/modules/security/clamav.py`` writes the
four clamav/scan cols; ``app/api/routes/files.py`` constructs ``File(...)`` with
``kind``/``company_id``; ``app/modules/documents/packs.py`` filters
``scan_status == CLEAN``. On PostgreSQL (the ``alembic upgrade`` path) every one
of those raises ``UndefinedColumnError``. So this is real drift, not a rename or
intentional design — iter-47 takes the safe path: add the cols + indexes to
match the model (nullable cols carry no default; the three NOT NULL cols carry a
server_default so existing rows satisfy the constraint). Mirror of iter-42's
add_column+enum cohort.

RB-002 guard: ``kind`` / ``scan_status`` use ``SQLEnum(PyEnum)`` and the model
sets NO ``values_callable`` — so SQLAlchemy persists the member NAME (uppercase)
not the ``str`` ``.value`` (lowercase). The enum labels AND the NOT NULL
server_defaults are therefore declared in UPPERCASE, matching exactly what
``Base.metadata.create_all`` emits on PG. Lowercase would reintroduce the
RB-002 defect (a server_default that is not a valid enum label).

Enum lifecycle (Layer-3 fix, commit 7f92693): although ``op.add_column`` with a
native ``sa.Enum`` is *meant* to auto-emit ``CREATE TYPE`` on PG, under
``env.py``'s AUTOCOMMIT + ``transaction_per_migration`` that implicit create
proved unreliable across the DAG (it failed with ``type "file_kind" does not
exist``). So upgrade explicitly creates both enum types up front with
``checkfirst=True`` — the flag makes the create idempotent, so it is a safe no-op
(NOT a duplicate ``CREATE TYPE`` error) when the type already exists.
``drop_column`` does NOT auto-drop the type, so downgrade explicitly drops both
with ``checkfirst=True`` too.

Ordering: ``file`` is created by the universal root ``6b6dee7c951f`` (an ancestor
of every head) and the two enum types are self-created up front by this
migration via ``sa.Enum(...).create(checkfirst=True)``. There are no cross-branch
FK targets (``company_id`` / ``pack_id`` are plain String, no ForeignKey). So
``down_revision = iter38`` alone orders this correctly under ``alembic upgrade
heads`` — unlike iter-46, no ``depends_on`` is needed.

After iter-47 lands, column_drift_lite business-drift drops from 2 -> 1 table
(only ``outbox_events`` remains — the iter-48 candidate).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260529_iter47_file_business_cols"
down_revision: str | Sequence[str] | None = "20260529_iter38_server_default_c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# UPPERCASE enum NAME labels — the SA default storage form for
# ``Enum(EnumClass, name=X)`` without ``values_callable`` (RB-002 guard).
# Order mirrors the Python enum member order in app/models/file.py.
FILE_KIND_VALUES = ("TEMPLATE", "DOCUMENT", "ARCHIVE", "DRAFT", "ATTACHMENT", "OTHER")
FILE_SCAN_STATUS_VALUES = ("PENDING", "IN_PROGRESS", "CLEAN", "INFECTED", "ERROR")


def upgrade() -> None:
    # file.{8 business cols} -------------------------------------------------
    # Explicitly create the two PG enum types up front (checkfirst=True). Under
    # transaction_per_migration the implicit CREATE TYPE that add_column would
    # otherwise emit is unreliable across the DAG, so create them here (mirrors
    # next55 / 8d2c1a6c5e24). No-op on SQLite. NOT NULL cols carry a
    # server_default so existing rows satisfy the constraint.
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        postgresql.ENUM(*FILE_KIND_VALUES, name="file_kind", create_type=False).create(bind, checkfirst=True)
        postgresql.ENUM(*FILE_SCAN_STATUS_VALUES, name="file_scan_status", create_type=False).create(
            bind, checkfirst=True
        )
    op.add_column(
        "file",
        sa.Column("original_name", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "file",
        sa.Column(
            "kind",
            postgresql.ENUM(*FILE_KIND_VALUES, name="file_kind", create_type=False),
            nullable=False,
            server_default="DOCUMENT",
        ),
    )
    op.add_column(
        "file",
        sa.Column("company_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "file",
        sa.Column("pack_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "file",
        sa.Column(
            "is_quarantined",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    op.add_column(
        "file",
        sa.Column(
            "scan_status",
            postgresql.ENUM(*FILE_SCAN_STATUS_VALUES, name="file_scan_status", create_type=False),
            nullable=False,
            server_default="PENDING",
        ),
    )
    op.add_column(
        "file",
        sa.Column("clamav_signature", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "file",
        sa.Column("clamav_scanned_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Indexes (ix_file_storage_key / ix_file_sha256 already exist from
    # initial_schema — only the four involving NEW columns are added here).
    op.create_index("ix_file_company_id", "file", ["company_id"], unique=False)
    op.create_index("ix_file_pack_id", "file", ["pack_id"], unique=False)
    op.create_index("ix_file_kind", "file", ["tenant_id", "kind"], unique=False)
    op.create_index("ix_file_pack", "file", ["tenant_id", "pack_id"], unique=False)


def downgrade() -> None:
    # Reverse order so downstream tooling observes inverse symmetry.
    op.drop_index("ix_file_pack", table_name="file")
    op.drop_index("ix_file_kind", table_name="file")
    op.drop_index("ix_file_pack_id", table_name="file")
    op.drop_index("ix_file_company_id", table_name="file")

    op.drop_column("file", "clamav_scanned_at")
    op.drop_column("file", "clamav_signature")
    op.drop_column("file", "scan_status")
    op.drop_column("file", "is_quarantined")
    op.drop_column("file", "pack_id")
    op.drop_column("file", "company_id")
    op.drop_column("file", "kind")
    op.drop_column("file", "original_name")

    # drop_column does not auto-drop the PG enum types — drop them explicitly.
    sa.Enum(name="file_scan_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="file_kind").drop(op.get_bind(), checkfirst=True)
